import "./landing.css";

import { ArrowRight } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { Link } from "react-router";
import { TagLogo } from "../../app/TagLogo";
import { buttonClasses } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { Provenance } from "../../components/Provenance";
import { Stamp } from "../../components/Stamp";
import { useMediaQuery } from "../../lib/use-media-query";
import { AUDIENCES, JOURNEY, LIMITS, PROOF, ROLES, RULES, STEP_IDS, type Evidence } from "./content";
import { useStampCount } from "./stamps";

const TITLE = "VEYRA · Know every animal. Protect every asset.";
const DESCRIPTION =
  "VEYRA links each cow's muzzle-verified identity, value, camera observations, and insurance in one passport. An AI agent prepares; nothing financial moves until the manager stamps it. Sandbox demo.";
const WEB_TESTS = 116;
const API_TESTS = 462;

const CORNERS = ["tl", "tr", "br", "bl"] as const;

function usePageMeta() {
  useEffect(() => {
    const previousTitle = document.title;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const previousDescription = meta?.content;
    document.title = TITLE;
    if (meta) meta.content = DESCRIPTION;
    return () => {
      document.title = previousTitle;
      if (meta && previousDescription !== undefined) meta.content = previousDescription;
    };
  }, []);
}

function Hole() {
  return <span className="pitch-tag-hole" aria-hidden="true" />;
}

function PitchNav() {
  return (
    <header data-surface="shell" className="bg-shell text-on-shell">
      <nav aria-label="Primary" className="pitch-nav">
        <Link to="/" className="pitch-wordmark" aria-label="VEYRA, top of the page">
          <TagLogo className="h-[30px] w-6 flex-none" />
          <span>VEYRA</span>
        </Link>
        <ul className="pitch-nav-links">
          <li>
            <a href="#journey">How it works</a>
          </li>
          <li>
            <a href="#proof">Proof</a>
          </li>
          <li>
            <a href="#limits">Limits</a>
          </li>
          <li>
            <a href="#run">Run it</a>
          </li>
        </ul>
        <Link to="/herd" className="pitch-nav-cta">
          Open the live demo
        </Link>
      </nav>
    </header>
  );
}

function Hero({ tagRef }: { tagRef: RefObject<HTMLDivElement | null> }) {
  return (
    <section className="pitch-hero" aria-labelledby="pitch-title">
      <div ref={tagRef} className="pitch-tag pitch-tag-hero">
        <Hole />
        <span className="pitch-tag-number figures" aria-hidden="true">
          001
        </span>
        <h1 id="pitch-title" className="pitch-display">
          Know every animal. Protect every asset.
        </h1>
        <p className="pitch-sub">
          One passport per cow links its muzzle-based identity, its value, what the cameras saw, and its insurance.
        </p>
        <p className="pitch-who">For farm managers, livestock insurers, and the vets between them.</p>
      </div>

      <div className="pitch-side">
        <p className="pitch-lead">
          An AI agent prepares the application, the premium, the notification, and the claim. Nothing financial moves
          until the manager stamps the exact line.
        </p>
        <div className="pitch-cta">
          <Link to="/herd" className={buttonClasses("primary", "md", "pitch-btn")}>
            Open the live demo
          </Link>
          <a href="#journey" className={buttonClasses("secondary", "md", "pitch-btn")}>
            Watch the 5-minute journey
          </a>
        </div>
        <p className="text-sm text-muted">
          Sandbox only: no real money, fictional policies, every AI output labeled live, prototype, or simulated.
        </p>
        <ul className="pitch-hero-stamps" aria-label="What VEYRA has measured">
          <li>
            <Stamp kind="posted" text="Identity · muzzle match" className="pitch-stamp-lg" />
            <span className="pitch-fact">
              <b className="figures">92.5%</b> correct at threshold, <b className="figures">1.4%</b> unknown-animal false
              match · held-out test animals, US feedlot photos
            </span>
          </li>
          <li>
            <Stamp kind="approved" text="Tracked · barn CCTV" className="pitch-stamp-lg" />
            <span className="pitch-fact">
              Recall <b className="figures">0.997</b>, MOTA <b className="figures">0.976</b> · 8-Calves test video, 10 min, one pen
            </span>
          </li>
          <li>
            <Stamp kind="approved" text="Weighed · photo path" className="pitch-stamp-lg" />
            <span className="pitch-fact">
              <b className="figures">8.7%</b> MAPE on the photo path with withers height from a tape,{" "}
              <b className="figures">5.4%</b> with tape heart girth · 71 cattle
            </span>
          </li>
          <li>
            <span className="pitch-next">Next stamp: covered · awaiting you</span>
          </li>
        </ul>
      </div>
    </section>
  );
}

/**
 * Stamps that land in one batch (a jump to a later step) press one after another. Each keeps its
 * press until its own animation ends, so a fast scroll never strips a press halfway through.
 */
function usePressing(count: number, reduced: boolean) {
  const [seen, setSeen] = useState(count);
  const [pressing, setPressing] = useState<ReadonlyMap<number, number>>(() => new Map());
  if (count !== seen) {
    setSeen(count);
    if (count > seen && !reduced) {
      const next = new Map(pressing);
      for (let index = seen; index < count; index++) next.set(index, (index - seen) * 140);
      setPressing(next);
    }
  }
  const done = (index: number) =>
    setPressing((prev) => {
      if (!prev.has(index)) return prev;
      const next = new Map(prev);
      next.delete(index);
      return next;
    });
  return { pressing, done };
}

/**
 * The traveling tag, sticky beside the story. It appears only once the hero tag has left the
 * viewport (a hand-off, not a second tag), reads "Tag 001" until Sari is enrolled, then collects
 * one dated stamp per journey step.
 */
function Companion({ count, reduced, shown }: { count: number; reduced: boolean; shown: boolean }) {
  const { pressing, done } = usePressing(count, reduced);
  const enrolled = count > 0;
  return (
    <aside className="pitch-companion-col" aria-labelledby="companion-name">
      <div className="pitch-tag pitch-tag-companion" data-shown={shown ? "" : undefined}>
        <Hole />
        <span className="pitch-tag-number pitch-tag-number-sm figures" aria-hidden="true">
          001
        </span>
        <p id="companion-name" className="text-lg font-heavy">
          {enrolled ? "Sari · 001" : "Tag 001"}
        </p>
        <p className={enrolled ? "figures text-sm" : "text-sm"}>{enrolled ? "animal-demo-001" : "Not enrolled yet"}</p>
        <p className="sr-only">
          {count} of {JOURNEY.length} journey steps stamped.
        </p>
        <ol className="pitch-companion-stamps">
          {JOURNEY.map((step, index) => {
            const stamped = index < count;
            const delay = pressing.get(index);
            return (
              <li key={step.id}>
                <a href={`#step-${step.id}`} className="pitch-companion-link">
                  {stamped ? (
                    <span
                      className="pitch-press"
                      style={{ "--press-delay": `${delay ?? 0}ms` } as CSSProperties}
                      onAnimationEnd={() => done(index)}
                    >
                      <Stamp kind={step.kind} text={step.stamp} press={delay !== undefined} />
                    </span>
                  ) : (
                    <span className="pitch-slot">{step.title}</span>
                  )}
                  <span className="sr-only">{stamped ? ", stamped" : ", not reached yet"}</span>
                </a>
              </li>
            );
          })}
          <li>
            <Link to="/herd" className="pitch-slot pitch-slot-action">
              Awaiting your stamp
              <ArrowRight aria-hidden="true" className="size-4 flex-none" strokeWidth={2.5} />
              <span className="sr-only">: open the live demo</span>
            </Link>
          </li>
        </ol>
      </div>
    </aside>
  );
}

/** Whether the element is on screen: false once it has scrolled out (true without IntersectionObserver). */
function useOnScreen(ref: RefObject<Element | null>): boolean {
  const [onScreen, setOnScreen] = useState(true);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => setOnScreen(entries.at(-1)?.isIntersecting ?? true));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return onScreen;
}

function Shot({ image, guard = false }: { image: Evidence; guard?: boolean }) {
  return (
    <figure className="pitch-shot" data-guard={guard ? "" : undefined}>
      <div className="evidence-frame">
        <picture>
          {image.mobile && (
            <source
              media="(max-width: 39.9375rem)"
              srcSet={image.mobile.src}
              width={image.mobile.width}
              height={image.mobile.height}
            />
          )}
          <img src={image.src} alt={image.alt} width={image.width} height={image.height} loading="lazy" decoding="async" />
        </picture>
        {CORNERS.map((corner) => (
          <svg key={corner} className="reg-mark" data-corner={corner} viewBox="0 0 18 18" aria-hidden="true" focusable="false">
            <path d="M1.5 18V1.5H18" fill="none" stroke="currentColor" strokeWidth="3" />
          </svg>
        ))}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="font-bold">{image.caption}</span>
        <span className="flex items-center gap-2 text-sm text-muted">
          App screenshot, demo data
          <Provenance source="simulated" />
        </span>
      </figcaption>
    </figure>
  );
}

function SectionHead({ id, title, children }: { id: string; title: string; children?: ReactNode }) {
  return (
    <header className="pitch-section-head">
      <h2 id={id} className="pitch-h2">
        {title}
      </h2>
      {children && <div className="pitch-intro">{children}</div>}
    </header>
  );
}

function Problem() {
  const records = [
    { name: "Ear-tag register", where: "a book or spreadsheet in the office", gap: "A tag number, with nothing proving which animal wears it." },
    { name: "Valuation sheet", where: "the manager's spreadsheet", gap: "A price, with no link to the animal's identity or its date." },
    { name: "Barn CCTV", where: "a recorder in the barn", gap: "Footage of cattle, with no identity attached." },
    { name: "Insurance policy", where: "a PDF from the insurer", gap: "Cover for an animal, checked by hand at claim time." },
  ];
  return (
    <section id="problem" className="pitch-section" aria-labelledby="problem-title">
      <SectionHead id="problem-title" title="Four records in four places">
        <p>Each one is about the same cow, and none of them can point to the others.</p>
      </SectionHead>
      <ul className="pitch-ledger">
        {records.map((record) => (
          <li key={record.name} className="pitch-ledger-row pitch-ledger-row-3">
            <span className="font-bold">{record.name}</span>
            <span className="text-muted">{record.where}</span>
            <span>{record.gap}</span>
          </li>
        ))}
        <li className="pitch-ledger-total">
          <EarTag animalId="animal-demo-001" state="confirmed" size="md" />
          <p>
            <b>One passport.</b> Identity, value, what the cameras saw, and the cover, all on{" "}
            <span className="figures">animal-demo-001</span>, with every change in its passbook.
          </p>
        </li>
      </ul>
    </section>
  );
}

function Journey() {
  return (
    <section id="journey" className="pitch-section" aria-labelledby="journey-title">
      <SectionHead id="journey-title" title="One cow, five stamps">
        <p>
          Follow Sari, <span className="figures">animal-demo-001</span>, through the five-minute demo as a manager would.
          Every screen below is the running app; its demo data is labeled simulated.
        </p>
      </SectionHead>
      <ol className="pitch-steps">
        {JOURNEY.map((step, index) => (
          <li key={step.id} id={`step-${step.id}`} className="pitch-step">
            <div className="pitch-step-gutter figures" aria-hidden="true">
              <span className="pitch-step-number">{index + 1}</span>
              <span className="text-sm text-muted">of {JOURNEY.length}</span>
            </div>
            <div className="pitch-step-text">
              <h3 className="pitch-h3">
                <span className="sr-only">Step {index + 1}: </span>
                {step.title}
              </h3>
              <p>{step.body}</p>
              {/* Below 1024px the traveling tag steps aside, and each step carries its own stamp. */}
              <Stamp kind={step.kind} text={step.stamp} className="pitch-step-stamp" />
            </div>
            <Shot image={step.image} />
            {step.guard && <Shot image={step.guard} guard />}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Proof() {
  return (
    <section id="proof" className="pitch-section" aria-labelledby="proof-title">
      <SectionHead id="proof-title" title="Every figure, with its dataset and its limit">
        <p>
          From the evaluations in the repository (<span className="figures">services/api/models/MODEL_CARD.md</span> and{" "}
          <span className="figures">ml/results/</span>). They say what was measured, on what, and where it stops.
        </p>
      </SectionHead>
      <div className="dt-wrap">
        <table className="dt pitch-proof">
          <thead>
            <tr>
              <th scope="col">Claim</th>
              <th scope="col">Result</th>
              <th scope="col">Dataset</th>
              <th scope="col">Limit</th>
            </tr>
          </thead>
          <tbody>
            {PROOF.map((row) => (
              <tr key={row.claim}>
                <td data-primary="">
                  <span className="block font-bold">{row.claim}</span>
                  <span className="figures block text-sm text-muted">{row.model}</span>
                </td>
                <td data-label="Result">
                  <ul className="flex flex-col gap-1">
                    {row.results.map((result) => (
                      <li key={result.label}>
                        <b className="figures text-md">{result.figure}</b> <span className="text-sm">{result.label}</span>
                      </li>
                    ))}
                  </ul>
                </td>
                <td data-label="Dataset" className="text-sm">
                  {row.dataset}
                </td>
                <td data-label="Limit" className="text-sm">
                  {row.limit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Control() {
  return (
    <section id="control" className="pitch-section" aria-labelledby="control-title">
      <SectionHead id="control-title" title="The manager holds the pen">
        <p>The agent prepares; the wallet only moves on a stamp. These rules are enforced by the API and tested.</p>
      </SectionHead>
      <div className="pitch-split">
        <ul className="pitch-ledger">
          {RULES.map((item) => (
            <li key={item.rule} className="pitch-ledger-row">
              <p>
                <b>{item.rule}</b> {item.detail}
              </p>
            </li>
          ))}
        </ul>
        <Shot
          image={{
            src: "/pitch/approvals.webp",
            width: 1440,
            height: 1080,
            alt: "The Approvals screen after the manager stamped the premium payment: the history shows the policy application and the 87.36 USD premium, each with a green POSTED stamp, and the detail panel shows the payload hash, version 1, the evidence manifest, and the sandbox balance after.",
            caption: "Approvals · posted with the manager's stamp",
          }}
        />
      </div>
    </section>
  );
}

function Audience() {
  return (
    <section id="audience" className="pitch-section" aria-labelledby="audience-title">
      <SectionHead id="audience-title" title="Who it's for" />
      <ul className="pitch-ledger">
        {AUDIENCES.map((item) => (
          <li key={item.who} className="pitch-ledger-row pitch-ledger-row-2">
            <span className="text-md font-bold">{item.who}</span>
            <span>{item.line}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Limits() {
  return (
    <section id="limits" className="pitch-section" aria-labelledby="limits-title">
      <SectionHead id="limits-title" title="What it doesn't prove yet" />
      <ul className="pitch-ledger">
        {LIMITS.map((limit) => (
          <li key={limit} className="pitch-ledger-row">
            <p>{limit}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Run() {
  return (
    <section id="run" className="pitch-run" aria-labelledby="run-title">
      <div className="pitch-run-inner">
        <div className="flex flex-col gap-6">
          <h2 id="run-title" className="pitch-h2">
            Run it
          </h2>
          <p className="pitch-lead">The live demo is this app, on a sandbox. Open it as the manager and follow Sari.</p>
          <div>
            <Link to="/herd" className={buttonClasses("primary", "md", "pitch-btn")}>
              Open the live demo
            </Link>
          </div>
          <p>
            <span className="figures font-bold">{API_TESTS}</span> backend tests ·{" "}
            <span className="figures font-bold">{WEB_TESTS}</span> web tests · the PRD's{" "}
            <span className="figures font-bold">10</span> critical-verification checks, one test each.
          </p>
        </div>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h3 className="pitch-h3">On your machine</h3>
            <pre className="pitch-code">
              <code>docker compose up --build</code>
            </pre>
            <p>
              Serves on <span className="figures">http://localhost:8000</span>. Set{" "}
              <span className="figures">ANTHROPIC_API_KEY</span> to turn on Claude's explanations; without it, answers are
              labeled offline templates.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <h3 className="pitch-h3">Demo roles, from the role switcher</h3>
            <ul className="pitch-roles">
              {ROLES.map((item) => (
                <li key={item.role}>
                  <b>{item.role}</b> <span>({item.person})</span> {item.can}.
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer data-surface="shell" className="bg-shell text-on-shell">
      <div className="pitch-footer">
        <span className="flex items-center gap-2.5 text-md font-heavy">
          <TagLogo className="h-[30px] w-6 flex-none" />
          VEYRA
        </span>
        <p className="text-on-shell-muted">Sandbox demo · fictional policies · no real money</p>
        <Link to="/herd" className="pitch-footer-link">
          Open the live demo
        </Link>
      </div>
    </footer>
  );
}

/** The pitch page at "/": one ear tag carries the offer, then travels beside the story collecting stamps. */
export function LandingPage() {
  usePageMeta();
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const count = useStampCount(STEP_IDS, reduced);
  const heroTag = useRef<HTMLDivElement>(null);
  const heroOnScreen = useOnScreen(heroTag);
  return (
    <div className="pitch">
      <a
        href="#main"
        className="sr-only z-tooltip rounded-control bg-tag px-4 py-3 font-bold text-ink no-underline focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to main content
      </a>
      <PitchNav />
      <main id="main" tabIndex={-1} className="outline-none">
        <Hero tagRef={heroTag} />
        <div className="pitch-body">
          <Companion count={count} reduced={reduced} shown={!heroOnScreen} />
          <div className="pitch-sections">
            <Problem />
            <Journey />
            <Proof />
            <Control />
            <Audience />
            <Limits />
          </div>
        </div>
        <Run />
      </main>
      <Footer />
    </div>
  );
}
