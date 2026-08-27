#! /usr/bin/env python
"""
Decide which layers of a deployment's stack run for a given trigger.  A stack is
one deployment (dev, staging, prod); a layer is one tier within it: cluster,
support, nfs, nfs-volume, hub.  PR labels drive which layers deploy.

The caller passes a YAML layer spec in LAYER_SPEC.  On push the decision comes
from the PR labels and branch; on workflow_dispatch the inputs pass straight
through.

A shared_branch owns a cluster's shared infra, so that infra only deploys from
there, always before the hubs.  For prod it is 'staging'.

Each layer sets one GITHUB_OUTPUT key, named in its output field.  The rest of
the spec fields:
  label               set the output when this label is on the PR.
  always_on           on push, set the output regardless of label; the leaf
                      resolves specifics.  The prod hubs use it: their label
                      family is expanded by determine-hub-deployments.py.
  shared_branch_only  only set on shared_branch; other branches skip it.
  when_on/when_off    emit these instead of "true"/"false".
  implied_by          force this layer on whenever the named layer is on (the
                      NFS volume follows the NFS server, whose ClusterIP can
                      change under the immutable PV).
  requires            force this layer off unless the named layer's backend
                      already exists (BACKENDS_PRESENT) or is being created in
                      this run.  A layer cannot deploy into a missing cluster.
                      A requested layer skipped this way is reported as a
                      GitHub Actions notice annotation.
  destroy_label       on push, this label on the merged PR makes the layer emit
                      "destroy" instead of its on/off value (gated the same as
                      the layer's own label).  Only meaningful on a when_on
                      layer whose leaf understands "destroy" (the cluster).  It
                      is the only path to a teardown: dispatch offers no destroy
                      choice, so prod can only be torn down through a labelled,
                      reviewable PR.
  environment_output  set to "prod" on refs/heads/prod, else shared_branch.

A "destroy" value forces every plain true/false layer off.  The calling workflow
carries the same spec with per-field comments.
"""

import argparse
import os
import sys
from collections import OrderedDict, namedtuple

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False

# One layer of the stack, as an immutable record.  Fields are documented in the
# module docstring.
Layer = namedtuple(
    "Layer",
    [
        "output",
        "label",
        "shared_branch_only",
        "when_on",
        "when_off",
        "implied_by",
        "requires",
        "destroy_label",
        "always_on",
    ],
    defaults=(None, False, None, None, None, None, None, False),
)


def _load(text: str) -> dict:
    """Parse a YAML string into a dict, treating empty input as {}."""
    return _yaml.load(text) or {}


def _on_value(layer: "Layer") -> str:
    """The value a layer's output carries when it is on."""
    return layer.when_on if layer.when_on is not None else "true"


def _off_value(layer: "Layer") -> str:
    """The value a layer's output carries when it is off."""
    return layer.when_off if layer.when_off is not None else "false"


def decide(
    event: str,
    ref: str,
    labels: str,
    spec: dict,
    dispatch_inputs: dict,
    backends_present: "set[str]",
) -> "tuple[OrderedDict[str, str], list]":
    """Return the output key -> value map and any layers skipped for a missing
    backend, as (output, required) pairs, for one trigger."""
    layers = [Layer(**item) for item in spec["layers"]]
    shared_branch = spec["shared_branch"]
    env_output = spec.get("environment_output")
    results: OrderedDict[str, str] = OrderedDict()

    if event == "workflow_dispatch":
        for layer in layers:
            results[layer.output] = dispatch_inputs[layer.output]
        if env_output:
            results[env_output] = dispatch_inputs[env_output]
    else:
        present = set(labels.split())
        on_shared_branch = ref == f"refs/heads/{shared_branch}"
        for layer in layers:
            gated_on = not layer.shared_branch_only or on_shared_branch
            enabled = (layer.always_on or layer.label in present) and gated_on
            if layer.when_on is not None:
                # A destroy label (same branch gating) overrides apply/skip.
                if (
                    layer.destroy_label is not None
                    and layer.destroy_label in present
                    and gated_on
                ):
                    results[layer.output] = "destroy"
                else:
                    results[layer.output] = layer.when_on if enabled else layer.when_off
            else:
                results[layer.output] = "true" if enabled else "false"
        if env_output:
            results[env_output] = "prod" if ref == "refs/heads/prod" else shared_branch

    # Apply implied_by before the destroy check below, so destroy still wins.
    for layer in layers:
        if layer.implied_by is not None and results.get(layer.implied_by) == "true":
            results[layer.output] = "true"

    # A layer can only deploy into a backend that exists.  Force it off unless
    # the required layer's backend is already present (BACKENDS_PRESENT) or is
    # being created in this run (its output sits at its on-value, e.g.
    # cluster_command == "apply").  Runs after implied_by so a missing backend
    # overrides an implied-on layer.
    by_output = {layer.output: layer for layer in layers}
    suppressed = []
    for layer in layers:
        if layer.requires is None:
            continue
        required = by_output.get(layer.requires)
        activating = required is not None and results.get(layer.requires) == _on_value(
            required
        )
        if layer.requires not in backends_present and not activating:
            if results[layer.output] == _on_value(layer):
                suppressed.append((layer.output, layer.requires))
            results[layer.output] = _off_value(layer)

    # A destroyed stack has nothing to deploy into.
    destroying = any(
        layer.when_on is not None and results[layer.output] == "destroy"
        for layer in layers
    )
    if destroying:
        for layer in layers:
            if layer.when_on is None:
                results[layer.output] = "false"

    return results, suppressed


def main(args: argparse.Namespace) -> None:
    results, suppressed = decide(
        event=os.environ.get("EVENT", ""),
        ref=os.environ.get("REF", ""),
        labels=os.environ.get("LABELS", ""),
        spec=_load(os.environ["LAYER_SPEC"]),
        dispatch_inputs=_load(os.environ.get("DISPATCH_INPUTS", "")),
        backends_present=set(os.environ.get("BACKENDS_PRESENT", "").split()),
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as fh:
            fh.writelines(f"{key}={value}\n" for key, value in results.items())

    print("  ".join(f"{key}: {value}" for key, value in results.items()))

    # Tell whoever merged that a requested layer did not deploy, and why.  The
    # change is committed and applies on the next stand-up of its backend.
    if suppressed:
        layers = ", ".join(
            f"{output} (needs {required})" for output, required in suppressed
        )
        print(
            f"::notice title=Layers not deployed::{layers} skipped: required "
            "backend is not present. The change is committed and will deploy "
            "on the next stack stand-up."
        )

    if args.debug:
        _yaml.dump(results, sys.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Also print the decision as YAML.",
    )
    main(parser.parse_args())
