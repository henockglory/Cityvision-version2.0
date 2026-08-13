package identity

import (
	"encoding/json"
	"testing"
)

func TestCompilePlateCompositionFRLike(t *testing.T) {
	raw, _ := json.Marshal([]PlateSegment{
		{Charset: "A-Z", Count: 2},
		{Charset: "0-9", Count: 4},
		{Charset: "A-Z", Count: 2},
	})
	re, err := CompilePlateComposition(raw)
	if err != nil {
		t.Fatal(err)
	}
	want := "^[A-Z]{2}[0-9]{4}[A-Z]{2}$"
	if re != want {
		t.Fatalf("got %q want %q", re, want)
	}
}

func TestCompilePlateCompositionRejectsEmpty(t *testing.T) {
	_, err := CompilePlateComposition(json.RawMessage(`[]`))
	if err == nil {
		t.Fatal("expected error")
	}
}
