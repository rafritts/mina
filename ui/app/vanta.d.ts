declare module 'vanta/dist/vanta.dots.min' {
  import type * as THREE from 'three'
  interface VantaEffect { destroy: () => void }
  interface VantaOptions { el: HTMLElement; THREE: typeof THREE; [key: string]: unknown }
  function DOTS(options: VantaOptions): VantaEffect
  export default DOTS
}

declare module 'vanta/dist/vanta.net.min' {
  import type * as THREE from 'three'
  interface VantaEffect { destroy: () => void }
  interface VantaOptions { el: HTMLElement; THREE: typeof THREE; [key: string]: unknown }
  function NET(options: VantaOptions): VantaEffect
  export default NET
}
