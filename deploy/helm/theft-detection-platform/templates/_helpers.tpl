{{- define "theft.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/component: {{ .name }}
app.kubernetes.io/part-of: {{ .root.Chart.Name }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
{{- end -}}

{{- define "theft.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{- define "theft.component" -}}
{{- $out := deepCopy .comp -}}
{{- range $k, $v := deepCopy .root.Values.defaults -}}
{{- if not (hasKey $out $k) -}}
{{- $_ := set $out $k $v -}}
{{- end -}}
{{- end -}}
{{- toYaml $out -}}
{{- end -}}

{{- define "theft.image" -}}
{{- if eq .root.Values.global.environment "prod" -}}
{{- if not .root.Values.global.image.registry -}}
{{- fail "global.image.registry is required when global.environment is prod" -}}
{{- end -}}
{{- if not .image.digest -}}
{{- fail (printf "image digest is required in prod for %s" .image.repository) -}}
{{- end -}}
{{- end -}}
{{- $repo := .image.repository -}}
{{- with .root.Values.global.image.registry -}}
{{- $repo = printf "%s/%s" . $repo -}}
{{- end -}}
{{- if .image.digest -}}
{{- printf "%s@%s" $repo .image.digest -}}
{{- else -}}
{{- printf "%s:%s" $repo (.image.tag | default .root.Chart.AppVersion) -}}
{{- end -}}
{{- end -}}

{{- define "theft.otelEnv" -}}
{{- $o := .root.Values.global.otel -}}
OTEL_SERVICE_NAME: {{ .serviceName | quote }}
OTEL_RESOURCE_ATTRIBUTES: {{ printf "service.namespace=theft,deployment.environment=%s,service.version=%s,service.name=%s" .root.Values.global.environment .root.Chart.AppVersion .serviceName | quote }}
OTEL_EXPORTER_OTLP_ENDPOINT: {{ $o.endpoint | quote }}
OTEL_EXPORTER_OTLP_PROTOCOL: {{ $o.protocol | quote }}
OTEL_TRACES_EXPORTER: {{ $o.tracesExporter | quote }}
OTEL_METRICS_EXPORTER: {{ $o.metricsExporter | quote }}
OTEL_LOGS_EXPORTER: {{ $o.logsExporter | quote }}
OTEL_PYTHON_LOG_CORRELATION: {{ $o.pythonLogCorrelation | quote }}
OTEL_PYTHON_LOG_FORMAT: {{ $o.pythonLogFormat | quote }}
{{- end -}}
