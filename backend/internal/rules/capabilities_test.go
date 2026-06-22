package rules

import (
	"encoding/json"
	"testing"
)

func TestScopesForCategory(t *testing.T) {
	tests := []struct {
		category string
		want     []string
	}{
		{"crowd", []string{"national"}},
		{"traffic", []string{"national"}},
		{"road-enforcement", []string{"national"}},
		{"presence", []string{"domestic"}},
		{"security", []string{"enterprise"}},
		{"spatial", []string{"enterprise"}},
		{"unknown-cat", []string{"enterprise"}},
	}
	for _, tc := range tests {
		got := scopesForCategory(tc.category)
		if len(got) != len(tc.want) || got[0] != tc.want[0] {
			t.Errorf("scopesForCategory(%q) = %v, want %v", tc.category, got, tc.want)
		}
	}
}

func TestEnrichCatalog_deploymentScopes(t *testing.T) {
	reg := &CapabilitiesRegistry{
		EventTypes: map[string]CapabilityMeta{},
		Templates: map[string]TemplateCapability{
			"tpl-override": {
				DeploymentScopes: []string{"domestic", "national"},
			},
		},
	}
	templates := []CatalogTemplate{
		{ID: "tpl-crowd", Category: "crowd"},
		{ID: "tpl-intrusion", Category: "security"},
		{ID: "tpl-home", Category: "presence"},
		{ID: "tpl-override", Category: "security"},
	}
	enriched := EnrichCatalog(templates, reg)

	byID := make(map[string]EnrichedCatalogTemplate)
	for _, e := range enriched {
		byID[e.ID] = e
	}

	if got := byID["tpl-crowd"].DeploymentScopes; len(got) != 1 || got[0] != "national" {
		t.Fatalf("crowd scopes = %v, want [national]", got)
	}
	if got := byID["tpl-intrusion"].DeploymentScopes; len(got) != 1 || got[0] != "enterprise" {
		t.Fatalf("security scopes = %v, want [enterprise]", got)
	}
	if got := byID["tpl-home"].DeploymentScopes; len(got) != 1 || got[0] != "domestic" {
		t.Fatalf("presence scopes = %v, want [domestic]", got)
	}
	if got := byID["tpl-override"].DeploymentScopes; len(got) != 2 || got[0] != "domestic" || got[1] != "national" {
		t.Fatalf("override scopes = %v, want [domestic national]", got)
	}
}

func TestEnrichCatalog_emptyRegistry(t *testing.T) {
	templates := []CatalogTemplate{{ID: "tpl-x", Category: "incident", Definition: json.RawMessage(`{}`)}}
	enriched := EnrichCatalog(templates, nil)
	if len(enriched) != 1 {
		t.Fatal("expected one enriched template")
	}
	if enriched[0].DeploymentScopes[0] != "national" {
		t.Fatalf("incident scope = %v", enriched[0].DeploymentScopes)
	}
}
