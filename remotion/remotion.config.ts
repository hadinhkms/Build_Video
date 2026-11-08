import { Config } from "@remotion/cli/config";
import { enableTailwind } from "@remotion/tailwind-v4";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setCrf(18);
Config.setTimeoutInMilliseconds(120000);
Config.setDelayRenderTimeoutInMilliseconds(120000);
Config.setChromiumOpenGlRenderer("angle");
Config.overrideWebpackConfig(enableTailwind);
