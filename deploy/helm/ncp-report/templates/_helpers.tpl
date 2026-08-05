{{- define "ncp-report.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ncp-report.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "ncp-report.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ncp-report.labels" -}}
app.kubernetes.io/name: {{ include "ncp-report.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "ncp-report.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ncp-report.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ncp-report.databaseHost" -}}
{{- if .Values.database.host -}}
{{- .Values.database.host -}}
{{- else -}}
{{- printf "%s-postgresql" (include "ncp-report.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "ncp-report.imagePullSecrets" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "ncp-report.databaseEnv" -}}
- name: REPORT_DB_ENABLED
  value: "true"
- name: REPORT_DB_REQUIRED
  value: "true"
- name: REPORT_DB_HOST
  value: {{ include "ncp-report.databaseHost" . | quote }}
- name: REPORT_DB_PORT
  value: {{ .Values.database.port | quote }}
- name: REPORT_DB_NAME
  value: {{ .Values.database.name | quote }}
- name: REPORT_DB_SSLMODE
  value: {{ .Values.database.sslmode | quote }}
{{- end -}}

{{- define "ncp-report.waitSchema" -}}
- name: wait-schema
  image: "{{ .Values.migration.image.repository }}:{{ .Values.migration.image.tag }}"
  imagePullPolicy: {{ .Values.migration.image.pullPolicy }}
  args: ["wait", {{ .Values.migration.schemaVersion | quote }}]
  env:
    - name: PGHOST
      value: {{ include "ncp-report.databaseHost" . | quote }}
    - name: PGPORT
      value: {{ .Values.database.port | quote }}
    - name: PGDATABASE
      value: {{ .Values.database.name | quote }}
    - name: PGUSER
      value: "ncp_msp_app"
    - name: PGPASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ .Values.existingSecret }}
          key: DB_MSP_APP_PASSWORD
    - name: PGSSLMODE
      value: {{ .Values.database.sslmode | quote }}
    - name: DB_WAIT_SECONDS
      value: {{ .Values.migration.waitSeconds | quote }}
  securityContext:
{{ toYaml .Values.containerSecurityContext | indent 4 }}
{{- end -}}
