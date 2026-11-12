// Study details shown on the consent page. Fill these in before running the study and have the
// consent text approved by the ethics committee. Change `consent_version` in the backend config
// (onboarding.consent_version) whenever this text changes; it is logged with every consent.
// Game numbers (payments, players, timers) are not set here: they come from the backend config.
const studyInfo = {
  title: "Island Economy: a group decision-making study",
  institution: "Max Planck Institute for Human Development, Berlin",
  // TODO before launch: researcher names, contact e-mail and ethics approval number.
  researchers: "[names of the researchers]",
  contactEmail: "[contact e-mail address]",
  ethicsApproval: "[ethics committee and approval number]",
  expectedMinutes: "[expected duration in minutes]",
};

export default studyInfo;
