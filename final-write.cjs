/*
 * PlanExpiry Lab: Final Write Boundary
 * Run: node final-write.cjs            (Node.js, no dependencies)
 * Run: node final-write.cjs --self-test
 *
 * A fictional provider owns slot, price, approval and unrelated records.
 * Global and scoped policies use the same atomic compare-and-append model;
 * global compares the whole revision, scoped compares the two required rows.
 * A client-only shadow records what it would decide but never writes.
 * One synchronous in-memory transition stands in for a real transaction.
 * No networking, identities, durable journal, clocks, or production claims.
 *
 * Motivation: Chen, Wang & Brinton, Fresh Memory, Stale Plans, Appendix F:
 * https://arxiv.org/html/2609.03340v2#A6
 * Global and scoped CAS are fictional comparators, not their implementations.
 * A validator for one HTTP resource does not cover independent services:
 * https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1
 */
"use strict";
const request = Object.freeze({key:"booking-1", slot:"S1", time:"14:00", price:30});
const canonical = r => JSON.stringify([r.slot,r.time,r.price]);
const approved = canonical(request);
const initial = () => ({
  revision:0, slotRev:0, approvalRev:0, open:true, price:30,
  approval:approved, journal:[]
});
const events = {
  unrelated: s => ({...s, revision:s.revision+1}),
  close: s => ({...s, revision:s.revision+1, slotRev:s.slotRev+1, open:false}),
  reopen: s => ({...s, revision:s.revision+1, slotRev:s.slotRev+1, open:true}),
  price: s => ({...s, revision:s.revision+1, slotRev:s.slotRev+1, price:31}),
  revoke: s => ({...s, revision:s.revision+1, approvalRev:s.approvalRev+1, approval:null})
};
const observe = s => ({revision:s.revision, slotRev:s.slotRev, approvalRev:s.approvalRev});
function decide(s, r, proof, policy, supported) {
  const out = (code, reason, receipt=null) => ({next:s, code, reason, receipt});
  const old = s.journal.find(row => row.key===r.key);
  if (old) return old.payload===canonical(r)
    ? out("REPLAY","recorded_receipt",old.receipt)
    : out("DENY","key_payload_mismatch");
  if (!supported) return out("HOLD","unsupported");
  if (s.approval!==canonical(r)) return out("DENY","approval_scope");
  const fields = policy==="global" ? ["revision"] : ["slotRev","approvalRev"];
  if (!["slotRev","approvalRev", ...fields].every(k => Number.isSafeInteger(proof?.[k])))
    return out("HOLD","missing_proof");
  if (fields.some(k => s[k]!==proof[k])) return out("HOLD","revision_conflict");
  if (!s.open || s.price!==r.price) return out("HOLD","slot_or_price");
  const receipt = Object.freeze({booking:s.journal.length+1});
  const row = Object.freeze({key:r.key,payload:canonical(r),receipt});
  const next = {...events.close(s), journal:[...s.journal,row]};
  return {next,code:"COMMIT",reason:"conditions_met",receipt};
}
// These eight scenarios are equally weighted challenge cases, not traffic.
const cases = [
  ["clean",[]], ["unrelated",["unrelated"]], ["slot_changed",["close"]],
  ["reverted_slot",["close","reopen"]], ["price_changed",["price"]],
  ["approval_revoked",["revoke"]], ["proof_missing",[]], ["unsupported",[]]
];
function evaluate() {
  return cases.map(([name,steps]) => {
    const before=initial(), after=steps.reduce((s,k)=>events[k](s),before);
    const proof=observe(before);
    if(name==="proof_missing") delete proof.approvalRev;
    const supported=name!=="unsupported";
    // Staleness for the shadow includes ABA: the slot returned to its old
    // value, but the evidence is from an earlier slot revision.
    const shadowWouldAllow = name!=="proof_missing";
    const shadowStale = shadowWouldAllow &&
      (before.slotRev!==after.slotRev || before.approvalRev!==after.approvalRev);
    const run = p => {
      const x=decide(after,request,proof,p,supported);
      const effects=x.next.journal.length-after.journal.length;
      return {code:x.code,reason:x.reason,effects,staleEffects:effects*Number(shadowStale),
              providerChecks:1};
    };
    return {name, evidenceReads:1, global:run("global"), scoped:run("scoped"),
            shadow:{wouldAllow:shadowWouldAllow,wouldBeStale:shadowStale,effects:0}};
  });
}
function report() {
  const rows=evaluate();
  const summarize = p => ({
    commits:rows.filter(r=>r[p].code==="COMMIT").length,
    holds:rows.filter(r=>r[p].code==="HOLD").length,
    denials:rows.filter(r=>r[p].code==="DENY").length,
    unnecessaryHolds:rows.filter(r=>r.name==="unrelated" && r[p].code==="HOLD").length,
    effects:rows.reduce((n,r)=>n+r[p].effects,0),
    staleEffects:rows.reduce((n,r)=>n+r[p].staleEffects,0),
    evidenceReads:rows.reduce((n,r)=>n+r.evidenceReads,0),
    providerChecks:rows.reduce((n,r)=>n+r[p].providerChecks,0)
  });
  return {fixtureCases:rows.length,global:summarize("global"),scoped:summarize("scoped"),
    shadow:{wouldBeStale:rows.filter(r=>r.shadow.wouldBeStale).length, effects:0},rows};
}
function selfTest() {
  const check=(ok,msg)=>{if(!ok) throw new Error(msg);};
  const expected = {
    clean:["COMMIT","COMMIT"],unrelated:["HOLD","COMMIT"],slot_changed:["HOLD","HOLD"],
    reverted_slot:["HOLD","HOLD"],price_changed:["HOLD","HOLD"],
    approval_revoked:["DENY","DENY"],proof_missing:["HOLD","HOLD"],unsupported:["HOLD","HOLD"]
  };
  for(const row of evaluate()) for(const [i,p] of ["global","scoped"].entries()) {
    const outcome=row[p], want=expected[row.name][i];
    check(outcome.code===want,row.name+" "+p);
    check(outcome.effects===Number(want==="COMMIT") && outcome.staleEffects===0,"effect count");
    check(row.shadow.effects===0,"shadow writes");
  }
  for(const p of ["global","scoped"]) {
    const s=initial(), proof=observe(s), first=decide(s,request,proof,p,true);
    check(s.open && s.journal.length===0 && !first.next.open,"atomic state transition");
    const replay=decide(first.next,request,proof,p,true);
    check(replay.code==="REPLAY" && replay.receipt===first.receipt &&
          replay.next===first.next && replay.next.journal.length===1,"exact replay");
    const clash=decide(first.next,{...request,time:"15:00"},proof,p,true);
    check(clash.code==="DENY" && clash.next===first.next,"key misuse");
    const wrong=decide(s,{...request,slot:"S2"},proof,p,true);
    check(wrong.code==="DENY" && wrong.next.journal.length===0,"scope");
    for(const a of Object.keys(events)) for(const b of Object.keys(events)) {
      const end=events[b](events[a](s)), x=decide(end,request,proof,p,true);
      const commit=p==="scoped" && a==="unrelated" && b==="unrelated";
      check((x.code==="COMMIT")===commit && x.next.journal.length===Number(commit),
          "two-event enumeration: "+p+" "+a+" "+b);
    }
  }
  return "PASS: 16 case-policy checks, 8 state/replay/scope checks, 50 ordered two-event cases";
}
if (typeof module!=="undefined") {
  module.exports={report,selfTest};
  if(require.main===module) console.log(process.argv.includes("--self-test")
    ? selfTest() : JSON.stringify(report(),null,2));
}
