#!/usr/bin/env node
"use strict";

// Synthetic evidence routing; nothing calls a network or performs an action.
// Each endpoint returns either its authoritative Boolean or unavailable (-1).
const endpoints = [
  ["approval-primary", 0, 1], ["capacity-primary", 1, 1],
  ["approval-mirror", 0, 1], ["capacity-mirror", 1, 1],
  ["approval-alt", 0, 2], ["capacity-alt", 1, 2],
];
const BUDGET = 5;
const NO = -1;
function verdict(trail) {
  const known = [];
  for (const [i, value] of trail) if (value !== NO) known[endpoints[i][1]] = value;
  return known.includes(0) ? "DENY" : known[0] === 1 && known[1] === 1 ? "ALLOW" : "HOLD";
}
function worlds(correlation, coupled = 0, prevalence = 0.8) {
  const out = [];
  // Blend independent cheap endpoints with a common cheap-service outage.
  // The second blend controls whether the nominal alternate shares that outage.
  for (const shared of [0, 1]) for (const joined of [0, 1]) {
    const blend = (shared ? correlation : 1 - correlation) * (joined ? coupled : 1 - coupled);
    if (!blend) continue;
    const rates = [prevalence, prevalence, 0.8];
    if (!shared) rates.push(0.8, 0.8, 0.8);
    rates.push(...(joined ? [0.875, 0.875] : [0.7, 0.7]));
    for (let mask = 0; mask < 2 ** rates.length; mask++) {
      const bits = rates.map((_, i) => (mask >> i) & 1);
      const p = rates.reduce((x, rate, i) => x * (bits[i] ? rate : 1 - rate), blend);
      const [approval, capacity, primary, ...rest] = bits;
      const cheap = shared ? Array(4).fill(primary) : [primary, ...rest.slice(0, 3)];
      const alt = bits.slice(-2).map(up => joined ? up && primary : up);
      const availability = cheap.concat(alt);
      out.push({ p, facts: [approval, capacity], observations: availability.map(
        (up, i) => up ? [approval, capacity][endpoints[i][1]] : NO
      ) });
    }
  }
  return out;
}
function orders(xs) {
  return xs.length ? xs.flatMap((x, i) => orders(xs.filter((_, j) => i !== j)).map(t => [x, ...t])) : [[]];
}
const ids = endpoints.map((_, i) => i);
function fixed(order) {
  return (t, budget) => {
    const next = order.find(i => !t.some(([j]) => i === j));
    return next !== undefined && endpoints[next][2] <= budget ? next : null;
  };
}
function runner(policy, world) {
  const trail = [];
  let budget = BUDGET;
  while (verdict(trail) === "HOLD") {
    const next = policy(trail, budget);
    if (next === null) break;
    if (!ids.includes(next) || trail.some(([j]) => next === j) || endpoints[next][2] > budget) {
      throw Error("Invalid or over-budget policy");
    }
    budget -= endpoints[next][2];
    trail.push([next, world.observations[next]]);
  }
  const result = verdict(trail);
  const truth = world.facts.every(Boolean) ? "ALLOW" : "DENY";
  if (result !== "HOLD" && result !== truth) throw Error("Wrong conclusive result");
  return [result, BUDGET - budget, trail];
}
function evaluate(policy, evidence) {
  const out = { ALLOW: 0, DENY: 0, HOLD: 0, cost: 0 };
  for (const world of evidence) {
    const [result, cost] = runner(policy, world);
    out[result] += world.p;
    out.cost += cost * world.p;
  }
  return out;
}
function better(a, b) {
  return a.resolved > b.resolved + 1e-10 ||
    (Math.abs(a.resolved - b.resolved) <= 1e-10 && a.cost < b.cost - 1e-10);
}
function trainFixed(evidence) {
  let best = { resolved: -1, cost: Infinity };
  let policy;
  for (const order of orders(ids)) {
    const candidate = fixed(order);
    const r = evaluate(candidate, evidence);
    const score = { resolved: r.ALLOW + r.DENY, cost: r.cost };
    if (better(score, best)) [best, policy] = [score, candidate];
  }
  return policy;
}
const key = trail => [...trail].sort((a, b) => a[0] - b[0]).map(pair => pair.join(":")).join(",");
function trainAdaptive(evidence) {
  const tree = new Map();
  function solve(trail, budget, remaining) {
    const k = key(trail);
    if (tree.has(k)) return tree.get(k);
    const mass = remaining.reduce((s, w) => s + w.p, 0);
    const proven = verdict(trail) !== "HOLD";
    let best = { resolved: proven ? mass : 0, cost: 0, next: null };
    if (!proven && mass) for (const i of ids) {
      const cost = endpoints[i][2];
      if (cost > budget || trail.some(([j]) => i === j)) continue;
      const score = { resolved: 0, cost: cost * mass, next: i };
      for (const o of [NO, 0, 1]) {
        const subset = remaining.filter(w => w.observations[i] === o);
        if (!subset.length) continue;
        const sub = solve([...trail, [i, o]], budget - cost, subset);
        score.resolved += sub.resolved;
        score.cost += sub.cost;
      }
      if (better(score, best)) best = score;
    }
    tree.set(k, best);
    return best;
  }
  const optimum = solve([], BUDGET, evidence);
  return { optimum, policy: t => tree.get(key(t))?.next ?? null };
}
function main() {
  const independent = worlds(0);
  const model = worlds(0.85);
  const sensors = trainAdaptive(independent);
  const aware = trainAdaptive(model);
  const policies = {
    "best fixed (independent model)": trainFixed(independent),
    "best fixed (dependency model)": trainFixed(model),
    "adaptive (independent model)": sensors.policy,
    "adaptive (dependency model)": aware.policy,
  };
  const scenarios = {
    "all cheap endpoints independent": independent,
    "held out: 95% common cheap outage regime": worlds(0.95),
    "held out: alternate often shares outage": worlds(0.95, 0.85),
    "held out: common outages and more denials": worlds(0.95, 0, 0.65),
  };
  const results = {};
  for (const [label, evidence] of Object.entries(scenarios)) {
    results[label] = Object.fromEntries(Object.entries(policies).map(([name, policy]) => {
      const { ALLOW, DENY, HOLD, cost } = evaluate(policy, evidence);
      return [name, { allowPct: +(100 * ALLOW).toFixed(2), denyPct: +(100 * DENY).toFixed(2),
        resolvedPct: +(100 * (ALLOW + DENY)).toFixed(2),
        holdPct: +(100 * HOLD).toFixed(2), checkUnits: +cost.toFixed(3) }];
    }));
  }
  function close(x, y) {
    if (Math.abs(x - y) > 1e-9) throw Error("Expected " + x + " ~= " + y);
  }
  for (const evidence of Object.values(scenarios)) close(evidence.reduce((s, w) => s + w.p, 0), 1);
  for (const [trained, evidence] of [[sensors, independent], [aware, model]]) {
    const r = evaluate(trained.policy, evidence);
    close(r.ALLOW + r.DENY, trained.optimum.resolved);
    close(r.cost, trained.optimum.cost);
    const base = evaluate(trainFixed(evidence), evidence);
    if (better({resolved: base.ALLOW + base.DENY, cost: base.cost}, trained.optimum)) throw Error("Exact planner worse than fixed baseline");
  }
  const marginal = (es, predicate) => es.reduce((s, w) => s + w.p * Number(predicate(w.observations)), 0);
  close(marginal(independent, o => o[0] === NO && o[2] === NO), .04);
  close(marginal(worlds(1), o => o[0] === NO && o[2] === NO), .2);
  close(marginal(worlds(1), o => o[0] === NO && o[4] !== NO), .14);
  close(marginal(worlds(1, 1), o => o[0] === NO && o[4] !== NO), 0);
  close(marginal(worlds(1, 1), o => o[4] !== NO), .7);
  for (const approval of [0, 1]) for (const capacity of [0, 1])
    for (let mask = 0; mask < 64; mask++) {
      const world = { facts: [approval, capacity],
        observations: endpoints.map(([, f], i) => (mask >> i) & 1 ? [approval, capacity][f] : NO) };
      for (const policy of Object.values(policies)) runner(policy, world);
      if (!mask) for (const policy of Object.values(policies)) {
        if (runner(policy, world)[0] !== "HOLD") throw Error("Unavailable must not imply DENY or ALLOW");
      }
    }
  console.log(JSON.stringify(results, null, 2));
}
main();
