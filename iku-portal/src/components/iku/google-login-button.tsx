"use client";

import { useEffect, useRef, useState } from "react";

export type GoogleLoginConfig = { apiKey: string; clientId: string; projectId: string };

type CredentialResponse = { credential?: string };

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            callback: (response: CredentialResponse) => void;
          }) => void;
          renderButton: (element: HTMLElement, options: Record<string, string | number>) => void;
        };
      };
    };
  }
}

type Props = {
  disabled?: boolean;
  onCredential: (credential: string, config: GoogleLoginConfig) => void;
};

export function GoogleLoginButton({ disabled = false, onCredential }: Props) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const callbackRef = useRef(onCredential);
  const [config, setConfig] = useState<GoogleLoginConfig | null>(null);
  const [configLoaded, setConfigLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  callbackRef.current = onCredential;

  useEffect(() => {
    let active = true;
    fetch("/api/auth/google-config", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Google sign-in is not configured");
        return await response.json() as GoogleLoginConfig & { configured: boolean };
      })
      .then((value) => {
        if (!active) return;
        if (!value.configured || !value.apiKey || !value.clientId || !value.projectId) {
          setUnavailable(true);
          return;
        }
        setConfig(value);
      })
      .catch(() => {
        if (active) setUnavailable(true);
      })
      .finally(() => {
        if (active) setConfigLoaded(true);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const element = buttonRef.current;
    if (!config || !element) return;
    let active = true;
    const render = () => {
      if (!active || !window.google || !buttonRef.current) return;
      buttonRef.current.replaceChildren();
      window.google.accounts.id.initialize({
        client_id: config.clientId,
        callback: (response) => {
          if (response.credential) callbackRef.current(response.credential, config);
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        width: 320,
        locale: "pt-PT",
      });
    };

    const scriptId = "google-identity-services";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (window.google) {
      render();
    } else if (script) {
      script.addEventListener("load", render);
    } else {
      script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.addEventListener("load", render);
      script.addEventListener("error", () => setUnavailable(true), { once: true });
      document.head.appendChild(script);
    }

    return () => {
      active = false;
      script?.removeEventListener("load", render);
    };
  }, [config]);

  return (
    <div className="google-login" aria-busy={disabled}>
      {config && <div ref={buttonRef} className={disabled ? "google-login-button disabled" : "google-login-button"} />}
      {!config && configLoaded && (
        <p className="auth-message auth-error" role="status">
          {unavailable ? "O início de sessão Google não está configurado neste portal." : "A carregar Google…"}
        </p>
      )}
    </div>
  );
}
