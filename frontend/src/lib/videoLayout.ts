/** Layout rect for a video with object-fit: contain inside a container. */
export interface ContainedVideoRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function computeContainedRect(
  containerW: number,
  containerH: number,
  videoW: number,
  videoH: number,
): ContainedVideoRect {
  if (containerW <= 0 || containerH <= 0 || videoW <= 0 || videoH <= 0) {
    return { left: 0, top: 0, width: containerW, height: containerH };
  }
  const scale = Math.min(containerW / videoW, containerH / videoH);
  const width = videoW * scale;
  const height = videoH * scale;
  return {
    left: (containerW - width) / 2,
    top: (containerH - height) / 2,
    width,
    height,
  };
}
