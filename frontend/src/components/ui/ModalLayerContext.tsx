import { createContext, useContext, type ReactNode } from 'react';
import { LAYER } from '@/lib/layerZIndex';

const ModalLayerContext = createContext<number | null>(null);

export function ModalLayerProvider({
  zIndex = LAYER.modalDropdown,
  children,
}: {
  zIndex?: number;
  children: ReactNode;
}) {
  return <ModalLayerContext.Provider value={zIndex}>{children}</ModalLayerContext.Provider>;
}

export function useModalLayerZIndex(): number | null {
  return useContext(ModalLayerContext);
}
