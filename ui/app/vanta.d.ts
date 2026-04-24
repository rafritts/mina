declare module 'vanta/dist/vanta.dots.min' {
  import type * as THREE from 'three'
  interface VantaEffect { destroy: () => void; setOptions: (opts: Record<string, unknown>) => void }
  interface VantaOptions { el: HTMLElement; THREE: typeof THREE; [key: string]: unknown }
  function DOTS(options: VantaOptions): VantaEffect
  export default DOTS
}

declare module 'vanta/dist/vanta.topology.min' {
  interface VantaEffect { destroy: () => void; setOptions: (opts: Record<string, unknown>) => void }
  interface VantaOptions { el: HTMLElement; p5: unknown; [key: string]: unknown }
  function TOPOLOGY(options: VantaOptions): VantaEffect
  export default TOPOLOGY
}
