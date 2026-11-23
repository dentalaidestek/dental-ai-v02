const staticConfig = require("./app.json");

module.exports = ({ config }) => {
  const projectId = String(process.env.EXPO_PUBLIC_EAS_PROJECT_ID || "").trim();
  const currentExtra = config.extra || staticConfig.expo.extra || {};
  const extra = { ...currentExtra };

  // The EAS project ID is public routing metadata, not a credential. Keep it
  // out of source control and inject it only in a configured build environment.
  if (projectId) {
    extra.eas = { ...(currentExtra.eas || {}), projectId };
  }

  return { ...config, extra };
};
