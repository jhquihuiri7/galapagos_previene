/**
 * Base temporal de la composición.
 *
 * Las animaciones se escribieron contando frames a 30 fps. Para poder subir la
 * tasa sin retocar cada número, todas esas cantidades pasan por `f()`, que las
 * traduce a la tasa real. Los tiempos del guion, en cambio, se declaran en
 * segundos y no dependen de esto.
 */

export const FPS = 60;

/** Tasa en que se midieron los frames autorales. */
const FPS_BASE = 30;

/** Frames medidos a 30 fps -> frames de la composición. */
export const f = (frames: number) => Math.round((frames * FPS) / FPS_BASE);
