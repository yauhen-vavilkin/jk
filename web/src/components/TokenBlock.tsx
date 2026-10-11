// Every page, while Jenkins refuses the token: nothing JK does can work without
// one, so the page is covered until Jenkins accepts it.
import { useEffect, useRef } from "react";

import { useCheckToken, useJenkinsStatus } from "@/api/queries";
import { PrimaryButton } from "@/components/ui/primitives";

export default function TokenBlock({ children }: { children: React.ReactNode }) {
  const status = useJenkinsStatus();
  const check = useCheckToken();
  const page = useRef<HTMLDivElement>(null);
  const refused = status.data?.auth_ok === false;

  // Asked on every open: a token can be revoked while JK keeps running.
  const ask = check.mutate;
  useEffect(() => ask(), [ask]);

  // Covered is not enough: Tab must not reach what is under the cover either.
  useEffect(() => {
    if (page.current) page.current.inert = refused;
  }, [refused]);

  return (
    <div className="relative min-h-0">
      <div ref={page} className="grid h-full grid-rows-[minmax(0,1fr)]">
        {children}
      </div>
      {refused && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-bg/90">
          <div role="alertdialog" aria-labelledby="token-title" aria-describedby="token-fix" className="flex max-w-[460px] flex-col gap-3 rounded-md border border-hairline bg-surface px-6 py-5">
            <h2 id="token-title" className="text-[16px] font-semibold text-warn">
              Jenkins rejected the API token
            </h2>
            <p id="token-fix" className="text-[14px] text-key">
              Put a new token in JENKINS_API_TOKEN in .env, run docker compose up -d, then check again.
            </p>
            <div className="flex justify-end">
              {/* On while a check runs, so it can take the focus as the cover appears. */}
              <PrimaryButton autoFocus onClick={() => !check.isPending && check.mutate()}>
                {check.isPending ? "Checking…" : "Check again"}
              </PrimaryButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
