#! /usr/bin/env python
"""
Decide which layers of a deployment's stack run for a given trigger.  A stack is
one deployment (dev, staging, prod); a layer is one tier within it —
cluster, support, nfs, nfs-volume, hub.  We can add more stacks in the future for
other deployments, or more layers to extend an existing one.  This script relies
on PR labels to direct the workflow to deploy the correct layers.

The caller passes a YAML layer spec in LAYER_SPEC.  On push the decision comes
from the PR labels and branch; on workflow_dispatch the inputs pass straight
through.

A shared_branch is a branch that owns a cluster's shared infra.  This is done
on purpose, as we want to limit when we deploy our core infrastructure (always
before we deploy actual hubs).  For our prod deployments, this will always be
'staging'.

Each layer names one GITHUB_OUTPUT key in its output field and sets that key
when the layer's label is present.  A shared_branch_only layer is set only on
shared_branch, so merging to any other branch skips it.  A layer with a
when_on/when_off pair emits those values; one without emits "true"/"false".
Optional environment_output adds a key set to "prod" on refs/heads/prod, else
shared_branch.  If any layer's value comes out as "destroy", the plain
true/false layers are all forced off.
The calling workflow carries the same spec with per-field comments.
"""

import argparse
import os
import sys
from collections import OrderedDict, namedtuple

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False

# One layer of the stack, as an immutable record.  Set when_on/when_off to emit
# custom values; leave them unset and the layer emits "true"/"false".
Layer = namedtuple(
    "Layer",
    ["output", "label", "shared_branch_only", "when_on", "when_off"],
    defaults=(False, None, None),
)


def _load(text: str) -> dict:
    """Parse a YAML string into a dict, treating empty input as {}."""
    return _yaml.load(text) or {}


def decide(
    event: str,
    ref: str,
    labels: str,
    spec: dict,
    dispatch_inputs: dict,
) -> "OrderedDict[str, str]":
    """Return the output key -> value map for one trigger."""
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
            enabled = layer.label in present and (
                not layer.shared_branch_only or on_shared_branch
            )
            if layer.when_on is not None:
                results[layer.output] = layer.when_on if enabled else layer.when_off
            else:
                results[layer.output] = "true" if enabled else "false"
        if env_output:
            results[env_output] = "prod" if ref == "refs/heads/prod" else shared_branch

    # A destroyed stack has nothing to deploy into.
    destroying = any(
        layer.when_on is not None and results[layer.output] == "destroy"
        for layer in layers
    )
    if destroying:
        for layer in layers:
            if layer.when_on is None:
                results[layer.output] = "false"

    return results


def main(args: argparse.Namespace) -> None:
    results = decide(
        event=os.environ.get("EVENT", ""),
        ref=os.environ.get("REF", ""),
        labels=os.environ.get("LABELS", ""),
        spec=_load(os.environ["LAYER_SPEC"]),
        dispatch_inputs=_load(os.environ.get("DISPATCH_INPUTS", "")),
    )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as fh:
            for key, value in results.items():
                fh.write(f"{key}={value}\n")

    print("  ".join(f"{key}: {value}" for key, value in results.items()))
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
