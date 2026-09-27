{{- define "data.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
app.kubernetes.io/part-of: theft-detection-platform
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
{{- end -}}

{{- define "data.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{- define "data.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 999
runAsGroup: 999
fsGroup: 999
fsGroupChangePolicy: OnRootMismatch
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "data.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop:
    - ALL
{{- end -}}

{{- define "data.certificate" -}}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: {{ .name }}
  namespace: {{ .root.Release.Namespace }}
  labels:
    {{- include "data.labels" (dict "root" .root "name" .name "component" "tls") | nindent 4 }}
spec:
  secretName: {{ .secretName }}
  commonName: {{ .identity }}
  duration: {{ .root.Values.certificates.duration }}
  renewBefore: {{ .root.Values.certificates.renewBefore }}
  privateKey:
    algorithm: ECDSA
    size: 256
    rotationPolicy: Always
  usages:
    - digital signature
    - server auth
    - client auth
  uris:
    - {{ printf "spiffe://%s/service/%s" .root.Values.certificates.trustDomain .identity }}
  dnsNames:
    {{- toYaml .dnsNames | nindent 4 }}
  ipAddresses:
    - 127.0.0.1
  {{- if .combined }}
  additionalOutputFormats:
    - type: CombinedPEM
  {{- end }}
  issuerRef:
    name: {{ .root.Values.issuer.name }}
    kind: {{ .root.Values.issuer.kind }}
    group: cert-manager.io
{{- end -}}
