/**
 * Clear a native gallery draft without opening a crash window.
 *
 * The encrypted vault is referenced by the SecureStore intent. Delete that
 * durable reference first; only then is it safe to sweep unreferenced files.
 * If best-effort cleanup fails, the next patient visit runs the same scoped
 * orphan reconciliation and removes the residue without losing the draft.
 */
export async function clearClinicalMediaDraft(
  deleteDurableIntent: () => Promise<void>,
  cleanupOrphanedFiles: () => Promise<unknown>,
): Promise<void> {
  await deleteDurableIntent();
  try {
    await cleanupOrphanedFiles();
  } catch {
    // The durable intent is already gone. Startup reconciliation owns residue.
  }
}
