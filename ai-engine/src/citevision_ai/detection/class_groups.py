"""COCO class group matching (mirrors shared/detection-classes.json)."""

CLASS_GROUP_MEMBERS: dict[str, frozenset[str]] = {
    "person": frozenset({"person"}),
    "vehicle": frozenset({"car", "truck", "bus", "motorcycle", "train", "boat"}),
    "bicycle": frozenset({"bicycle"}),
    "animal": frozenset({
        "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe",
    }),
    "baggage": frozenset({"backpack", "handbag", "suitcase"}),
    "any": frozenset(),
}


def matches_class_filter(class_name: str, class_filter: str) -> bool:
    if not class_filter or class_filter == "any":
        return True
    if class_name == class_filter:
        return True
    members = CLASS_GROUP_MEMBERS.get(class_filter)
    if members is not None:
        return class_name in members if members else True
    return class_name == class_filter
