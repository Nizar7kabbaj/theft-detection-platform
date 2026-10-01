{{- define "theft.principal" -}}
{{- printf "%s/ns/%s/sa/%s" .root.Values.networkPolicy.ambient.trustDomain (.namespace | default .root.Release.Namespace) .sa -}}
{{- end -}}

{{- define "theft.sourcePrincipal" -}}
{{- $peer := index .root.Values.networkPolicy.peers .name -}}
{{- if index .root.Values.components .name -}}
{{- include "theft.principal" (dict "root" .root "sa" .name) -}}
{{- else if and $peer $peer.serviceAccount -}}
{{- include "theft.principal" (dict "root" .root "sa" $peer.serviceAccount "namespace" $peer.namespace) -}}
{{- else -}}
{{- fail (printf "mesh: %s has no service account for an authorization policy" .name) -}}
{{- end -}}
{{- end -}}

{{- define "theft.authz" }}
---
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: {{ .name }}
  namespace: {{ .root.Release.Namespace }}
  labels:
    {{- include "theft.labels" (dict "root" .root "name" .name) | nindent 4 }}
  {{- if .hook }}
  annotations:
    helm.sh/hook: pre-install,pre-upgrade
    helm.sh/hook-weight: "-15"
    helm.sh/hook-delete-policy: before-hook-creation
  {{- end }}
spec:
  selector:
    matchLabels:
      {{- toYaml .selector | nindent 6 }}
  action: ALLOW
  rules:
    {{- range $key, $r := .rules }}
    - from:
        - source:
            principals:
              {{- if $r.sa }}
              - {{ include "theft.principal" (dict "root" $.root "sa" $r.sa) | quote }}
              {{- else }}
              - {{ include "theft.sourcePrincipal" (dict "root" $.root "name" $r.from) | quote }}
              {{- end }}
      to:
        - operation:
            ports:
              {{- range $r.ports }}
              - {{ . | quote }}
              {{- end }}
    {{- end }}
{{- end -}}
