import { renderShareImage, shareImage } from "./share-image";

export const alt = shareImage.alt;
export const size = shareImage.size;
export const contentType = shareImage.contentType;

export default function OpengraphImage() {
  return renderShareImage();
}
