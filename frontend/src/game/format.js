// Display helpers. Every number shown to participants is derived from server data.

export const coins = (x, digits = 1) =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : Number(x).toFixed(digits);

export const signed = (x, digits = 1) => (x > 0 ? "+" : x < 0 ? "−" : "") + coins(Math.abs(x), digits);

export const PHASE_TITLES = {
  event: "Event",
  policy: "Policy",
  communication: "Talk",
  decision: "Decide",
  resolution: "Results",
};

const titleCase = (s) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// Describe an event from its multipliers (event names and effects come from the config).
// The insurance line is shown only where insurance can apply (it exists only under a coordinator's policy).
export function describeEvent(ev, showInsurance = false) {
  if (!ev) return { title: "", effects: [] };
  const effects = [];
  const pct = (m) => `${m > 1 ? "+" : "−"}${Math.round(Math.abs(m - 1) * 100)}%`;
  if (ev.harvest_mult !== 1) effects.push(`Fishing yield ${pct(ev.harvest_mult)} this round`);
  if (ev.regrowth_mult !== 1) effects.push(`Fish regrowth ${pct(ev.regrowth_mult)} this round`);
  if (ev.price_mult !== 1) effects.push(`Fish price ${pct(ev.price_mult)} this round`);
  if (ev.insurance_payout && showInsurance) effects.push("Storm insurance pays out");
  if (effects.length === 0) effects.push("Nothing unusual this round");
  return { title: titleCase(ev.name), effects };
}

export function describeRedistribution(rule) {
  return (
    {
      equal: "shared equally",
      need: "shared by need (poorer islanders get more)",
      contribution: "shared by contribution",
      infrastructure: "invested in infrastructure",
    }[rule] || rule
  );
}
