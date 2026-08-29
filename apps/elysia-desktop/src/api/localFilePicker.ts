import { open } from "@tauri-apps/plugin-dialog";

const ATTACHABLE_FILE_EXTENSIONS = [
  "txt",
  "md",
  "markdown",
  "csv",
  "xlsx",
  "json",
  "html",
  "htm",
  "pdf",
  "docx"
] as const;

const PROFILE_PHOTO_EXTENSIONS = ["jpg", "jpeg", "png", "webp"] as const;
const EDITABLE_IMAGE_EXTENSIONS = ["bmp", "gif", "jpg", "jpeg", "png", "tif", "tiff", "webp"] as const;

export async function openLocalAttachableFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: "Text, Markdown, Data, JSON, HTML, PDF, and DOCX",
        extensions: [...ATTACHABLE_FILE_EXTENSIONS]
      }
    ]
  });

  if (typeof selected !== "string") {
    return null;
  }

  return selected;
}

export const openLocalTextOrMarkdownFile = openLocalAttachableFile;

export async function openLocalProfilePhotoFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: "Profile photo image",
        extensions: [...PROFILE_PHOTO_EXTENSIONS]
      }
    ]
  });

  if (typeof selected !== "string") {
    return null;
  }

  return selected;
}

export async function openLocalEditableImageFile(): Promise<string | null> {
  const selected = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: "Image for a private GIMP working copy",
        extensions: [...EDITABLE_IMAGE_EXTENSIONS]
      }
    ]
  });

  return typeof selected === "string" ? selected : null;
}
