package evaluator

// Mirrors shared/detection-classes.json group_members.
var classGroupMembers = map[string][]string{
	"person":  {"person"},
	"vehicle": {"car", "truck", "bus", "motorcycle", "train", "boat"},
	"bicycle": {"bicycle"},
	"animal": {
		"bird", "cat", "dog", "horse", "sheep", "cow",
		"elephant", "bear", "zebra", "giraffe",
	},
	"baggage": {"backpack", "handbag", "suitcase"},
	"any":     {},
}

func matchesClass(className, filter string) bool {
	if filter == "" || filter == "any" {
		return true
	}
	if className == filter {
		return true
	}
	if members, ok := classGroupMembers[filter]; ok {
		if len(members) == 0 {
			return true
		}
		for _, m := range members {
			if m == className {
				return true
			}
		}
		return false
	}
	return className == filter
}
