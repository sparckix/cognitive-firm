export type SurfaceMode = 'projection_only' | 'kernel_intents'
export type SurfaceWriteClass = 'kernel_intent'

export interface AppSurfacePolicy {
  surfaceName: string
  mode: SurfaceMode
}

export function loadAppSurfacePolicy(env: NodeJS.ProcessEnv = process.env): AppSurfacePolicy {
  const rawMode = env.ORBIT_SURFACE_MODE || 'projection_only'
  if (rawMode !== 'projection_only' && rawMode !== 'kernel_intents') {
    throw new Error(
      `Invalid ORBIT_SURFACE_MODE=${rawMode}; expected projection_only or kernel_intents`,
    )
  }
  const mode: SurfaceMode = rawMode
  return {
    surfaceName: env.ORBIT_SURFACE_NAME || 'orbit',
    mode,
  }
}

export function surfaceWriteAllowed(
  policy: AppSurfacePolicy,
  writeClass: SurfaceWriteClass,
): { ok: true } | { ok: false, reason: string } {
  if (policy.mode === 'projection_only') {
    return {
      ok: false,
      reason: `${policy.surfaceName} is running in projection_only mode; write intents are disabled`,
    }
  }
  return { ok: true }
}
