package notify

import (
	"bytes"
	"html/template"
	"time"
)

// AlertEmailData feeds the premium HTML alert template.
type AlertEmailData struct {
	Title      string
	RuleName   string
	Severity   string // info | warning | critical
	CameraName string
	Location   string
	Plate      string
	FaceLabel  string
	EventType  string
	SpeedKmh   string
	OccurredAt string
	ClipURL    string
	// Images are referenced inline via cid: identifiers (see InlineImage.CID).
	Images []EmailImage
	// Extra rows shown in the details table (label -> value).
	Details []EmailDetail
	BrandName string
	MailHogURL string
}

type EmailImage struct {
	CID   string
	Label string
}

type EmailDetail struct {
	Label string
	Value string
}

func severityColor(sev string) string {
	switch sev {
	case "critical":
		return "#ef4444"
	case "warning":
		return "#f59e0b"
	default:
		return "#38bdf8"
	}
}

func severityLabelFR(sev string) string {
	switch sev {
	case "critical":
		return "Critique"
	case "warning":
		return "Avertissement"
	default:
		return "Information"
	}
}

var alertEmailTmpl = template.Must(template.New("alert").Funcs(template.FuncMap{
	"sevColor": severityColor,
	"sevLabel": severityLabelFR,
}).Parse(alertEmailHTML))

// RenderAlertEmail produces the premium dark-theme HTML email body.
func RenderAlertEmail(d AlertEmailData) (string, error) {
	if d.BrandName == "" {
		d.BrandName = "CitéVision"
	}
	if d.OccurredAt == "" {
		d.OccurredAt = time.Now().Format("02/01/2006 15:04:05")
	}
	var buf bytes.Buffer
	if err := alertEmailTmpl.Execute(&buf, d); err != nil {
		return "", err
	}
	return buf.String(), nil
}

const alertEmailHTML = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{.Title}}</title>
</head>
<body style="margin:0;padding:0;background:#0b1120;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#e2e8f0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b1120;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#0f172a;border:1px solid #1e293b;border-radius:16px;overflow:hidden;">

  <!-- Header -->
  <tr><td style="padding:20px 28px;background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border-bottom:1px solid #1e293b;">
    <table role="presentation" width="100%"><tr>
      <td style="font-size:18px;font-weight:700;color:#f8fafc;letter-spacing:0.3px;">
        <span style="color:#38bdf8;">●</span> {{.BrandName}}
      </td>
      <td align="right">
        <span style="display:inline-block;padding:5px 12px;border-radius:999px;font-size:12px;font-weight:600;color:#0b1120;background:{{sevColor .Severity}};">
          {{sevLabel .Severity}}
        </span>
      </td>
    </tr></table>
  </td></tr>

  <!-- Title -->
  <tr><td style="padding:24px 28px 8px 28px;">
    <h1 style="margin:0;font-size:22px;line-height:1.3;color:#f8fafc;">{{.Title}}</h1>
    {{if .RuleName}}<p style="margin:6px 0 0 0;font-size:13px;color:#94a3b8;">Règle déclenchée : <strong style="color:#cbd5e1;">{{.RuleName}}</strong></p>{{end}}
    <p style="margin:6px 0 0 0;font-size:13px;color:#94a3b8;">{{.OccurredAt}}{{if .CameraName}} · {{.CameraName}}{{end}}{{if .Location}} · {{.Location}}{{end}}</p>
  </td></tr>

  <!-- Proof images -->
  {{if .Images}}
  <tr><td style="padding:16px 28px 4px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      {{range .Images}}
      <td style="padding:0 6px;" valign="top">
        <img src="cid:{{.CID}}" alt="{{.Label}}" width="262" style="width:100%;max-width:262px;border-radius:10px;border:1px solid #1e293b;display:block;">
        <p style="margin:6px 0 0 0;font-size:11px;color:#64748b;text-align:center;">{{.Label}}</p>
      </td>
      {{end}}
    </tr></table>
  </td></tr>
  {{end}}

  <!-- Details -->
  <tr><td style="padding:16px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #1e293b;border-radius:10px;overflow:hidden;">
      {{if .Plate}}<tr><td style="padding:10px 14px;font-size:13px;color:#94a3b8;background:#0b1120;width:40%;">Plaque</td><td style="padding:10px 14px;font-size:14px;color:#f8fafc;font-weight:600;letter-spacing:1px;">{{.Plate}}</td></tr>{{end}}
      {{if .FaceLabel}}<tr><td style="padding:10px 14px;font-size:13px;color:#94a3b8;background:#0b1120;">Identité</td><td style="padding:10px 14px;font-size:14px;color:#f8fafc;">{{.FaceLabel}}</td></tr>{{end}}
      {{if .SpeedKmh}}<tr><td style="padding:10px 14px;font-size:13px;color:#94a3b8;background:#0b1120;">Vitesse</td><td style="padding:10px 14px;font-size:14px;color:#f8fafc;font-weight:600;">{{.SpeedKmh}} km/h</td></tr>{{end}}
      {{if .EventType}}<tr><td style="padding:10px 14px;font-size:13px;color:#94a3b8;background:#0b1120;">Type</td><td style="padding:10px 14px;font-size:14px;color:#f8fafc;">{{.EventType}}</td></tr>{{end}}
      {{range .Details}}<tr><td style="padding:10px 14px;font-size:13px;color:#94a3b8;background:#0b1120;">{{.Label}}</td><td style="padding:10px 14px;font-size:14px;color:#f8fafc;">{{.Value}}</td></tr>{{end}}
    </table>
  </td></tr>

  <!-- Clip CTA -->
  {{if .ClipURL}}
  <tr><td style="padding:4px 28px 20px 28px;">
    <a href="{{.ClipURL}}" style="display:inline-block;padding:12px 22px;border-radius:10px;background:#38bdf8;color:#0b1120;font-size:14px;font-weight:700;text-decoration:none;">▶ Voir le clip vidéo (preuve)</a>
  </td></tr>
  {{end}}

  <!-- Footer -->
  <tr><td style="padding:16px 28px;border-top:1px solid #1e293b;background:#0b1120;">
    <p style="margin:0;font-size:11px;color:#475569;line-height:1.6;">
      Cet e-mail a été généré automatiquement par {{.BrandName}} suite à une détection vidéo.
      Les preuves (images, clip) sont conservées de manière sécurisée et horodatées.
      {{if .MailHogURL}}<br>Aperçu de la boîte de test : <a href="{{.MailHogURL}}" style="color:#38bdf8;">{{.MailHogURL}}</a>{{end}}
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>`
