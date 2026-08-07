import { createContext, useContext, useEffect, useState } from "react";
import { loadLotteryData } from "./data.js";

const DataContext = createContext(null);

export function DataProvider({ children }) {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadLotteryData()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", ...data });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", error });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <DataContext.Provider value={state}>{children}</DataContext.Provider>;
}

/** Returns { status: 'loading' | 'ready' | 'error', records?, summary?, schema?, error? } */
export function useLotteryData() {
  const ctx = useContext(DataContext);
  if (ctx === null) {
    throw new Error("useLotteryData must be used inside <DataProvider>");
  }
  return ctx;
}
