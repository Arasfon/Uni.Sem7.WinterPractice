from typing import List

from app.services.detector import BicycleBox


def _area(b: BicycleBox) -> float:
    return max(0.0, (b.x2 - b.x1)) * max(0.0, (b.y2 - b.y1))


def _iou(a: BicycleBox, b: BicycleBox) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0

    ua = _area(a) + _area(b) - inter
    return inter / ua if ua > 0 else 0.0


def _containment(outer: BicycleBox, inner: BicycleBox) -> float:
    ix1 = max(outer.x1, inner.x1)
    iy1 = max(outer.y1, inner.y1)
    ix2 = min(outer.x2, inner.x2)
    iy2 = min(outer.y2, inner.y2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    a_inner = _area(inner)
    return inter / a_inner if a_inner > 0 else 0.0


def _merge_group(group: List[BicycleBox]) -> BicycleBox:
    w = sum(max(1e-6, b.conf) for b in group)
    x1 = sum(b.x1 * b.conf for b in group) / w
    y1 = sum(b.y1 * b.conf for b in group) / w
    x2 = sum(b.x2 * b.conf for b in group) / w
    y2 = sum(b.y2 * b.conf for b in group) / w

    best = max(group, key=lambda b: b.conf)
    return BicycleBox(
        x1=float(x1),
        y1=float(y1),
        x2=float(x2),
        y2=float(y2),
        conf=float(best.conf),
        cls_id=best.cls_id,
        cls_name=best.cls_name,
    )


def postprocess_bicycle_boxes(
    boxes: List[BicycleBox],
    *,
    nms_iou: float = 0.45,
    dup_iou: float = 0.85,
    contain_thr: float = 0.90,
    contain_area_ratio: float = 1.40,
    contain_conf_margin: float = 0.05,
) -> List[BicycleBox]:
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: b.conf, reverse=True)

    kept: List[BicycleBox] = []
    for b in boxes:
        if all(_iou(b, k) < nms_iou for k in kept):
            kept.append(b)

    out: List[BicycleBox] = []
    for b in kept:
        drop = False
        for s in kept:
            if s is b:
                continue
            if _area(b) >= _area(s) * contain_area_ratio:
                if _containment(b, s) >= contain_thr and (b.conf <= s.conf + contain_conf_margin):
                    drop = True
                    break
        if not drop:
            out.append(b)

    merged: List[BicycleBox] = []
    used = [False] * len(out)
    for i, b in enumerate(out):
        if used[i]:
            continue
        group = [b]
        used[i] = True
        for j in range(i + 1, len(out)):
            if used[j]:
                continue
            if _iou(b, out[j]) >= dup_iou:
                group.append(out[j])
                used[j] = True
        merged.append(_merge_group(group) if len(group) > 1 else b)

    return merged
