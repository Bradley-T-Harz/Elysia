import { invoke } from "@tauri-apps/api/core";

export type SelectedIdentityPhoto = { sourcePath: string; previewUrl: string };

export async function chooseIdentityPhoto(): Promise<SelectedIdentityPhoto | null> {
  const selected = await invoke<SelectedIdentityPhoto | null>("choose_identity_photo");
  if (!selected) return null;
  const image = new Image();
  image.src = selected.previewUrl;
  try {
    await image.decode();
    if (!image.naturalWidth || image.naturalWidth * image.naturalHeight > 40_000_000) throw new Error();
  } catch {
    throw new Error("This image cannot be opened. Choose a valid JPG, PNG, or WebP photo up to 10 MB and 40 megapixels.");
  }
  return selected;
}
