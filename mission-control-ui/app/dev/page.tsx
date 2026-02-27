import { notFound } from "next/navigation";
import DevClient from "./dev-client";

export const dynamic = "force-dynamic";

export default function DevPage() {
  if (process.env.NEXT_PUBLIC_ENABLE_DEV_UI !== "1") {
    notFound();
  }
  return <DevClient />;
}
