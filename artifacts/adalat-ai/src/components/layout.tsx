import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { useQueryClient } from "@tanstack/react-query";
import { Moon, Sun, LogOut } from "lucide-react";
import { useLogOut } from "@workspace/api-client-react";
import { useCurrentUser } from "@/hooks/use-current-user";
import { cn } from "@/lib/utils";
import { CourtLogoMark } from "./logo";

/**
 * The masthead of a printed cause list, not an application chrome bar.
 *
 * The nav carried an icon per entry and sat in a filled segmented control,
 * which is the shape a settings screen uses. A section bar under a masthead is
 * set in apparatus and marks the current section by thickening the rule under
 * it — the same mark the tab heads and the table columns use, so the whole app
 * signals "you are here" one way instead of four.
 */
const NAV = [
  { href: "/", label: "Case library" },
  { href: "/dashboard", label: "Chambers" },
  // Not "cause list": that is the case library, which lists matters still to
  // be called. This page is the record of ones already heard, which is the
  // opposite direction in time and was reading as a duplicate of the library.
  { href: "/history", label: "Appearances" },
  { href: "/evidence", label: "Statutes" },
];

function isCurrent(location: string, href: string): boolean {
  return location === href || (href !== "/" && location.startsWith(href));
}

function ThemeToggle() {
  const [dark, setDark] = useState(
    () => localStorage.getItem("adalat-theme") === "dark",
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("adalat-theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <button
      type="button"
      onClick={() => setDark((value) => !value)}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="flex h-8 w-8 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

/**
 * Who the record belongs to, and the way out.
 *
 * Renders nothing when signed out, so the same Layout wraps the sign-in page
 * without showing a name it does not have.
 *
 * Signing out clears the query cache and then reloads the page outright.
 *
 * Clearing alone was not enough and the failure was visible: the cookie went,
 * the sign-out control went, and the previous student's Chambers page stayed on
 * screen with their session still listed, because emptying the cache does not
 * reliably push already-mounted observers back through the auth gate. On a
 * shared university lab machine that is the exact leak this scoping exists to
 * prevent, so logout does not depend on cache semantics — the next student gets
 * a blank page and a fresh request.
 */
function SignedInAs() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const logOut = useLogOut({
    mutation: {
      onSettled: () => {
        queryClient.clear();
        window.location.assign(import.meta.env.BASE_URL || "/");
      },
    },
  });

  if (!user) return null;

  return (
    <div className="flex items-center gap-1.5 border-l border-rule pl-2.5">
      {/* Held back to the widest breakpoint and kept on one line: at tablet
          widths the name competed with the nav for the last of the row and
          both wrapped, splitting "Ayesha Khan" across two lines in the
          masthead. The sign-out control carries the meaning without it. */}
      <span className="apparatus hidden whitespace-nowrap text-muted-foreground lg:inline">
        {user.displayName}
      </span>
      <button
        type="button"
        onClick={() => logOut.mutate()}
        disabled={logOut.isPending}
        aria-label="Sign out"
        title="Sign out"
        className="rounded-sm p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

/**
 * `fullBleed` is for the courtroom and nothing else.
 *
 * The chamber sizes itself from the height it is given, so it needs the main
 * area to be a definite-height flex child rather than a padded document that
 * grows with its content — and it needs the colophon out of the way, because a
 * footer under a courtroom reads as the room having ended. Every other page
 * keeps the padded, scrolling shell.
 */
export function Layout({
  children,
  fullBleed = false,
}: {
  children: ReactNode;
  fullBleed?: boolean;
}) {
  const [location] = useLocation();

  return (
    <div
      className={cn(
        "flex w-full flex-col bg-background selection:bg-primary/20 selection:text-primary",
        fullBleed ? "h-svh min-h-[40rem] overflow-hidden" : "min-h-screen",
      )}
    >
      <header className="sticky top-0 z-40 border-b border-rule bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/85">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-6 px-4 py-3 sm:px-6 lg:px-8">
          {/* The name is set as a name, not as a logo tile. A cause list is
              headed by the court it belongs to, in the same face as the
              matters underneath it. */}
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-3 rounded-sm transition-opacity hover:opacity-85"
          >
            <CourtLogoMark size={34} />
            <div className="flex flex-col">
              {/* The name of the court is not a thing that wraps. */}
              <span className="whitespace-nowrap font-serif text-[1.375rem] font-normal leading-none tracking-[-0.02em] text-foreground">
                CourtSimulator
              </span>
              <span className="apparatus mt-1 text-muted-foreground">
                Pakistan superior judiciary
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-1">
            <nav className="mr-2 hidden items-stretch gap-5 sm:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isCurrent(location, item.href) ? "page" : undefined}
                  className={cn(
                    "apparatus whitespace-nowrap border-b-2 pb-0.5 pt-1 transition-colors",
                    isCurrent(location, item.href)
                      ? "border-foreground text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            <ThemeToggle />
            <SignedInAs />
          </div>
        </div>

        {/* The section bar wraps to its own row below the name on a phone,
            where the two cannot share a line without one of them truncating. */}
        <nav className="flex gap-5 overflow-x-auto border-t border-rule/60 px-4 py-2 sm:hidden">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isCurrent(location, item.href) ? "page" : undefined}
              className={cn(
                "apparatus shrink-0 whitespace-nowrap border-b-2 pb-0.5 transition-colors",
                isCurrent(location, item.href)
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>

      <main
        className={cn(
          "mx-auto w-full max-w-[1440px] flex-1",
          fullBleed
            ? "flex min-h-0 flex-col"
            : "px-4 py-8 sm:px-6 sm:py-10 lg:px-8",
        )}
      >
        {children}
      </main>

      {/* The colophon of the sheet: what the record is grounded in, and when.
          Set as one line of apparatus rather than as a footer of link columns,
          because there is exactly one fact here worth carrying. */}
      <footer className={cn("mt-auto border-t border-rule", fullBleed && "hidden")}>
        <div className="mx-auto flex max-w-[1440px] flex-col gap-2 px-4 py-5 sm:flex-row sm:items-baseline sm:justify-between sm:px-6 lg:px-8">
          <p className="apparatus text-muted-foreground">
            Grounded in PPC 1860 · CrPC 1898 · QSO 1984 · Constitution 1973
          </p>
          <p className="apparatus text-muted-foreground">
            CourtSimulator · 2026
          </p>
        </div>
      </footer>
    </div>
  );
}
