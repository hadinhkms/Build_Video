import { loadFont } from "@remotion/google-fonts/BeVietnamPro";

export const { fontFamily } = loadFont("normal", {
  weights: ["600", "700"],
  subsets: ["vietnamese", "latin"],
});
