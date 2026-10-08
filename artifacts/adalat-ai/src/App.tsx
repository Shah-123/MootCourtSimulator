import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Route, Switch, Router as WouterRouter } from 'wouter';
import { Layout } from './components/layout';

import { useCurrentUser } from '@/hooks/use-current-user';

import CasesPage from './pages/cases';
import DashboardPage from './pages/dashboard';
import EvidencePage from './pages/evidence';
import HistoryPage from './pages/history';
import SessionPage from './pages/session';
import SignInPage from './pages/sign-in';
import VerdictPage from './pages/verdict';

const queryClient = new QueryClient();

/**
 * Nothing renders until we know who is asking.
 *
 * This gates the shell, not the data. The API scopes every session query by the
 * cookie regardless of what the client renders; this only decides what the
 * student is shown, and is not what keeps one student's marks away from
 * another.
 */
function AuthGate({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useCurrentUser();

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="apparatus text-muted-foreground">Rising…</p>
      </div>
    );
  }

  // Deliberately not wrapped in Layout. The header carries the case-library
  // navigation and a signed-out visitor has nowhere to go with it — and because
  // Layout also renders the signed-in-as control, wrapping put a second observer
  // of this very query on the page, which is what made it loop.
  if (!user) {
    return (
      <div className="min-h-screen bg-background px-4">
        <SignInPage />
      </div>
    );
  }

  return <>{children}</>;
}

function Router() {
  return (
    <Switch>
      <Route path="/">
        <Layout><CasesPage /></Layout>
      </Route>
      <Route path="/dashboard">
        <Layout><DashboardPage /></Layout>
      </Route>
      <Route path="/history">
        <Layout><HistoryPage /></Layout>
      </Route>
      <Route path="/evidence">
        <Layout><EvidencePage /></Layout>
      </Route>
      {/* The only full-bleed route: the courtroom needs the whole viewport
          below the masthead, and sizes itself from the height it is given. */}
      <Route path="/sessions/:id">
        {params => (
          <Layout fullBleed>
            <SessionPage id={params.id} />
          </Layout>
        )}
      </Route>
      <Route path="/sessions/:id/verdict">
        {params => <Layout><VerdictPage /></Layout>}
      </Route>
      <Route>
        <Layout><NotFound /></Layout>
      </Route>
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <AuthGate>
            <Router />
          </AuthGate>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
