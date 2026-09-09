{{- /* Render a helm value as a python literal. Handles bools, strings and numbers. */ -}}
{{- define "python.literal" -}}
{{- if kindIs "bool" . -}}
{{ ternary "True" "False" . }}
{{- else if kindIs "string" . -}}
{{ printf "%q" . }}
{{- else -}}
{{ . }}
{{- end -}}
{{- end -}}
