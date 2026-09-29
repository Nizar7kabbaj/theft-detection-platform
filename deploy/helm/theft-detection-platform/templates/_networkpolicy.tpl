{{- define "theft.npOn" -}}
{{- $np := .root.Values.networkPolicy -}}
{{- $comp := index .root.Values.components .name -}}
{{- $peer := index $np.peers .name -}}
{{- if $comp -}}
{{- if $comp.enabled }}true{{ end -}}
{{- else if $peer -}}
{{- if ne (toString $peer.enabled) "false" }}true{{ end -}}
{{- else -}}
{{- fail (printf "networkPolicy: %s is neither a component nor a peer" .name) -}}
{{- end -}}
{{- end -}}

{{- define "theft.npPeer" -}}
{{- $np := .root.Values.networkPolicy -}}
{{- $comp := index .root.Values.components .name -}}
{{- $peer := index $np.peers .name -}}
{{- if $comp }}
- podSelector:
    matchLabels:
      {{- include "theft.selectorLabels" (dict "root" .root "name" .name) | nindent 6 }}
{{- else if and $peer $peer.cidrs }}
{{- range $peer.cidrs }}
- ipBlock:
    cidr: {{ . }}
{{- end }}
{{- else if $peer }}
- podSelector:
    matchLabels:
      {{- toYaml $peer.podLabels | nindent 6 }}
  {{- with $peer.namespace }}
  namespaceSelector:
    matchLabels:
      kubernetes.io/metadata.name: {{ . }}
  {{- end }}
{{- else }}
{{- fail (printf "networkPolicy: %s is neither a component nor a peer" .name) }}
{{- end }}
{{- end -}}

{{- define "theft.npDns" -}}
{{- with .Values.networkPolicy.dns }}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .namespace }}
      podSelector:
        matchLabels:
          {{- toYaml .podLabels | nindent 10 }}
  ports:
    - port: {{ .port }}
      protocol: UDP
    - port: {{ .port }}
      protocol: TCP
{{- end }}
{{- end -}}

{{- define "theft.npPorts" -}}
{{- $np := .root.Values.networkPolicy -}}
{{- $peer := index $np.peers .name -}}
{{- $ports := .ports -}}
{{- if and $np.ambient.enabled (not (and $peer $peer.cidrs)) -}}
{{- $ports = append $ports $np.ambient.hbonePort -}}
{{- end -}}
{{- range $ports }}
- port: {{ . }}
  protocol: TCP
{{- end }}
{{- end -}}

{{- define "theft.accessLabels" -}}
{{- $np := .root.Values.networkPolicy -}}
{{- if $np.enabled }}
{{- range .egress }}
{{- $peer := index $np.peers .to }}
{{- if and $peer $peer.access (ne (toString $peer.enabled) "false") }}
{{ printf "%s/%s" $np.accessLabelPrefix .to }}: "true"
{{- end }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "theft.npJob" }}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
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
  podSelector:
    matchLabels:
      {{- include "theft.selectorLabels" (dict "root" .root "name" .name) | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  egress:
    {{- include "theft.npDns" .root | trim | nindent 4 }}
    {{- range .root.Values.networkPolicy.jobEgress }}
    {{- if include "theft.npOn" (dict "root" $.root "name" .to) }}
    - to:
        {{- include "theft.npPeer" (dict "root" $.root "name" .to) | trim | nindent 8 }}
      ports:
        {{- include "theft.npPorts" (dict "root" $.root "name" .to "ports" .ports) | trim | nindent 8 }}
    {{- end }}
    {{- end }}
{{- end -}}
