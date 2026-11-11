// Communication step: group chat, private messages, and (coordinator condition) offers to the coordinator.
// Messages are plain text: React renders them as text, never as HTML.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { coins } from "../format";

const pct = (x) => `${Math.round(x * 100)}%`;

export function actorLabel(actor, snap) {
  if (actor === snap.actor) return "You";
  if (actor === "coordinator") return "Coordinator";
  return snap.labels[Number(actor.slice(1))];
}

function MessageList({ messages, snap, empty }) {
  const end = useRef(null);
  useEffect(() => {
    if (end.current) end.current.scrollTop = end.current.scrollHeight;
  }, [messages.length]);
  return (
    <Box
      ref={end}
      role="log"
      aria-live="polite"
      sx={{ height: 220, overflowY: "auto", p: 1, bgcolor: "action.hover", borderRadius: 1 }}
    >
      {messages.length === 0 && (
        <Typography variant="body2" color="text.secondary">{empty}</Typography>
      )}
      {messages.map((m) => {
        const mine = m.from === snap.actor;
        return (
          <Box key={m.id} sx={{ mb: 0.75, textAlign: mine ? "right" : "left" }}>
            <Typography variant="caption" color="text.secondary" display="block">
              {actorLabel(m.from, snap)}
              {m.to && !mine ? " → you" : ""}
              {m.to && mine ? ` → ${actorLabel(m.to, snap)}` : ""} · round {m.round}
            </Typography>
            <Typography
              variant="body2"
              sx={{
                display: "inline-block",
                maxWidth: "85%",
                px: 1,
                py: 0.5,
                borderRadius: 1.5,
                bgcolor: mine ? "primary.main" : "background.paper",
                color: mine ? "primary.contrastText" : "text.primary",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                textAlign: "left",
              }}
            >
              {m.text}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

function Composer({ snap, call, channel, to, disabled, placeholder }) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const max = snap.limits.message_max_chars;
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    const ack = await call("send_message", { channel, to, text });
    setBusy(false);
    if (ack.ok) {
      setText("");
      setError("");
    } else setError(ack.error || "Could not send");
  };
  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          size="small"
          fullWidth
          multiline
          maxRows={3}
          placeholder={placeholder}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value.slice(0, max))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          inputProps={{ maxLength: max, "aria-label": placeholder }}
          helperText={text.length > max * 0.8 ? `${text.length} / ${max}` : " "}
        />
        <Button variant="contained" onClick={send} disabled={busy || disabled || !text.trim()}>
          Send
        </Button>
      </Stack>
      {error && <Alert severity="error" sx={{ mt: 0.5 }}>{error}</Alert>}
    </Box>
  );
}

function PrivateMessages({ snap, call }) {
  const others = useMemo(() => {
    const list = snap.labels.map((_, i) => `p${i}`).filter((a) => a !== snap.actor);
    if (snap.has_coordinator && snap.actor !== "coordinator") list.push("coordinator");
    return list;
  }, [snap.labels, snap.actor, snap.has_coordinator]);
  const [to, setTo] = useState(others[0]);
  const thread = snap.messages.filter(
    (m) => m.channel === "direct" && ((m.from === snap.actor && m.to === to) || (m.from === to && m.to === snap.actor))
  );
  return (
    <>
      <FormControl size="small" fullWidth sx={{ mb: 1 }}>
        <InputLabel id="dm-to">Private conversation with</InputLabel>
        <Select labelId="dm-to" label="Private conversation with" value={to} onChange={(e) => setTo(e.target.value)}>
          {others.map((a) => (
            <MenuItem key={a} value={a}>{actorLabel(a, snap)}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <MessageList messages={thread} snap={snap} empty="No private messages yet. Only the two of you can see them." />
      <Composer snap={snap} call={call} channel="direct" to={to}
        placeholder={`Private message to ${actorLabel(to, snap)}`} />
    </>
  );
}

const STATUS = {
  pending: { label: "waiting for an answer", color: "default" },
  accepted: { label: "accepted", color: "success" },
  refused: { label: "refused", color: "default" },
  expired: { label: "not answered — returned", color: "default" },
};

function OfferStatus({ o, forCoordinator }) {
  const s = STATUS[o.status] || { label: o.status, color: "default" };
  let settled = "";
  if (o.settled) {
    if (o.settled.executed) settled = o.settled.detected ? "paid · discovered, fined" : "paid";
    else if (o.settled.reason === "cap_reached") settled = "not paid (limit reached)";
  }
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center">
      <Chip size="small" label={s.label} color={s.color} variant={o.status === "accepted" ? "filled" : "outlined"} />
      {settled && <Chip size="small" label={settled} variant="outlined" />}
      {forCoordinator && o.favor && <Chip size="small" label={`favor: ${FAVORS[o.favor]}`} variant="outlined" />}
    </Stack>
  );
}

function OfferTab({ snap, call }) {
  const L = snap.limits;
  const available = Math.max(0, snap.observation.wealth - snap.escrow);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const thisRound = snap.my_offers.filter((o) => o.round === snap.round);
  const a = Number(amount);
  const valid = amount !== "" && a >= L.bribe_min_amount && a <= available && thisRound.length < L.bribe_max_offers_per_round;
  const send = async () => {
    setBusy(true);
    const ack = await call("offer_bribe", { amount: a, note });
    setBusy(false);
    if (ack.ok) {
      setAmount("");
      setNote("");
      setError("");
    } else setError(ack.error || "Could not send the offer");
  };
  return (
    <>
      <Typography variant="body2" sx={{ mb: 1 }}>
        You can privately offer coins to the coordinator, with a note. Only the coordinator sees it. The coins are held
        until the coordinator answers; if the offer is refused or not answered in this step, you keep them. If the
        coordinator accepts, you pay at the end of the round. An accepted offer is discovered with a chance of{" "}
        {pct(L.bribe_detection_prob)}; then you and the coordinator each pay a fine of {coins(L.bribe_fine, 0)} coins.
      </Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField
          size="small"
          type="number"
          label="Coins"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputProps={{ min: L.bribe_min_amount, max: available, step: 1 }}
          helperText={`Available: ${coins(available)}`}
          sx={{ width: { sm: 140 } }}
        />
        <TextField
          size="small"
          fullWidth
          label="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value.slice(0, L.note_max_chars))}
          inputProps={{ maxLength: L.note_max_chars }}
          helperText=" "
        />
      </Stack>
      <Button variant="outlined" onClick={send} disabled={!valid || busy}>Send offer to the coordinator</Button>
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      {snap.my_offers.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Your offers</Typography>
          {[...snap.my_offers].reverse().map((o) => (
            <Paper key={o.id} variant="outlined" sx={{ p: 1, mt: 0.75 }}>
              <Typography variant="body2">
                Round {o.round}: <b>{coins(o.amount)} coins</b>
                {o.note ? ` — “${o.note}”` : ""}
              </Typography>
              <OfferStatus o={o} />
              {o.reply && (
                <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                  Coordinator: “{o.reply}”
                </Typography>
              )}
            </Paper>
          ))}
        </Box>
      )}
    </>
  );
}

export const FAVORS = {
  quota_exempt: "exempt from the quota",
  audit_immune: "never audited",
  double_redistribution_weight: "double share of the pot",
};

function TabLabel({ n, color = "primary", children }) {
  return (
    <Badge color={color} badgeContent={n} sx={{ "& .MuiBadge-badge": { right: -10 } }}>
      <Box component="span" sx={{ pr: n ? 0.5 : 0 }}>{children}</Box>
    </Badge>
  );
}

function useUnread(messages, filter, active) {
  const [seen, setSeen] = useState(() => messages.filter(filter).length);
  const n = messages.filter(filter).length;
  useEffect(() => {
    if (active) setSeen(n);
  }, [active, n]);
  return active ? 0 : Math.max(0, n - seen);
}

// Islanders' communication panel.
export function PlayerChat({ snap, call }) {
  const [tab, setTab] = useState("public");
  const pubUnread = useUnread(snap.messages, (m) => m.channel === "public" && m.from !== snap.actor, tab === "public");
  const dmUnread = useUnread(snap.messages, (m) => m.channel === "direct" && m.to === snap.actor, tab === "direct");
  const publicMsgs = snap.messages.filter((m) => m.channel === "public");
  return (
    <Box>
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} variant="fullWidth" sx={{ mb: 1 }}>
        <Tab value="public" aria-label="Group chat" label={<TabLabel n={pubUnread}>Group</TabLabel>} />
        <Tab value="direct" aria-label="Private messages" label={<TabLabel n={dmUnread}>Private</TabLabel>} />
        {snap.has_coordinator && !snap.coordinator_left && <Tab value="offer" aria-label="Offer to the coordinator" label="Offer" />}
      </Tabs>
      {tab === "public" && (
        <>
          <MessageList messages={publicMsgs} snap={snap}
            empty={`Nothing said yet. Everyone in the group${snap.has_coordinator ? ", including the coordinator," : ""} can read this chat.`} />
          <Composer snap={snap} call={call} channel="public" placeholder="Message to everyone" />
        </>
      )}
      {tab === "direct" && <PrivateMessages snap={snap} call={call} />}
      {tab === "offer" && <OfferTab snap={snap} call={call} />}
    </Box>
  );
}

function InboxOffer({ item, snap, call }) {
  const [reply, setReply] = useState("");
  const [favor, setFavor] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const room = snap.bribe_income_cap - snap.bribe_income_committed;
  const income = snap.bribe_income_rate * item.amount;
  const overCap = income > room + 1e-9;
  const answer = async (accept) => {
    setBusy(true);
    const ack = await call("respond_bribe", {
      offer_id: item.offer_id,
      accept,
      reply,
      favor: accept && favor ? favor : null,
    });
    setBusy(false);
    if (!ack.ok) setError(ack.error || "Could not answer");
  };
  const open = item.status === "pending" && item.round === snap.round && snap.phase === "communication";
  return (
    <Paper variant="outlined" sx={{ p: 1.25, mt: 1 }}>
      <Typography variant="body2">
        <b>{actorLabel(item.from, snap)}</b> offers you <b>{coins(item.amount)} coins</b> (round {item.round})
        {item.note ? ":" : "."}
      </Typography>
      {item.note && (
        <Typography variant="body2" sx={{ fontStyle: "italic", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          “{item.note}”
        </Typography>
      )}
      {open ? (
        <>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            If you accept, you earn {coins(income)} coins. {overCap ? "This would go over your limit, so you cannot accept it." : ""}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
            <TextField size="small" fullWidth label="Reply (optional)" value={reply}
              onChange={(e) => setReply(e.target.value.slice(0, snap.limits.message_max_chars))} />
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id={`fav-${item.offer_id}`}>Favor in return (optional)</InputLabel>
              <Select labelId={`fav-${item.offer_id}`} label="Favor in return (optional)" value={favor}
                onChange={(e) => setFavor(e.target.value)}>
                <MenuItem value="">No favor</MenuItem>
                {Object.entries(FAVORS).map(([k, v]) => (
                  <MenuItem key={k} value={k}>{v}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button variant="contained" color="success" disabled={busy || overCap} onClick={() => answer(true)}>Accept</Button>
            <Button variant="outlined" disabled={busy} onClick={() => answer(false)}>Refuse</Button>
          </Stack>
          {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        </>
      ) : (
        <Box sx={{ mt: 0.5 }}>
          <OfferStatus o={item} forCoordinator />
          {item.reply && <Typography variant="body2" sx={{ mt: 0.5 }}>You replied: “{item.reply}”</Typography>}
        </Box>
      )}
    </Paper>
  );
}

// Coordinator's communication panel: inbox (offers + private messages), group chat, private messages.
export function CoordinatorChat({ snap, call }) {
  const inbox = snap.observation.inbox;
  const pending = inbox.filter((m) => m.type === "bribe" && m.status === "pending" && m.round === snap.round).length;
  const [tab, setTab] = useState("inbox");
  const pubUnread = useUnread(snap.messages, (m) => m.channel === "public" && m.from !== snap.actor, tab === "public");
  const dmUnread = useUnread(snap.messages, (m) => m.channel === "direct" && m.to === snap.actor, tab === "direct");
  const offers = inbox.filter((m) => m.type === "bribe");
  const room = Math.max(0, snap.bribe_income_cap - snap.bribe_income_committed);
  return (
    <Box>
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} variant="fullWidth" sx={{ mb: 1 }}>
        <Tab value="inbox" aria-label="Offers" label={<TabLabel n={pending} color="error">Offers</TabLabel>} />
        <Tab value="public" aria-label="Group chat" label={<TabLabel n={pubUnread}>Group</TabLabel>} />
        <Tab value="direct" aria-label="Private messages" label={<TabLabel n={dmUnread}>Private</TabLabel>} />
      </Tabs>
      {tab === "inbox" && (
        <>
          {snap.coordinator_left ? (
            <Typography variant="body2" color="text.secondary">
              Because the rules are now fixed, islanders can no longer make offers.
            </Typography>
          ) : (
          <Typography variant="body2" color="text.secondary">
            Islanders can privately offer you coins. You earn {pct(snap.bribe_income_rate)} of an accepted offer, up to{" "}
            {coins(snap.bribe_income_cap, 0)} coins in the whole game ({coins(room)} left). An accepted offer is
            discovered with a chance of {pct(snap.limits.bribe_detection_prob)}; then you and the islander each pay a
            fine of {coins(snap.limits.bribe_fine, 0)} coins. Offers you do not answer in this step are refused.
          </Typography>
          )}
          {offers.length === 0 && !snap.coordinator_left && (
            <Typography variant="body2" sx={{ mt: 1 }}>No offers so far.</Typography>
          )}
          {[...offers].reverse().map((item) => (
            <InboxOffer key={item.offer_id} item={item} snap={snap} call={call} />
          ))}
        </>
      )}
      {tab === "public" && (
        <>
          <MessageList messages={snap.messages.filter((m) => m.channel === "public")} snap={snap}
            empty="Nothing said yet. Everyone in the group can read this chat." />
          <Composer snap={snap} call={call} channel="public" placeholder="Message to everyone" />
        </>
      )}
      {tab === "direct" && <PrivateMessages snap={snap} call={call} />}
    </Box>
  );
}
