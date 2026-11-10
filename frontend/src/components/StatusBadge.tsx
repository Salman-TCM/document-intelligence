import { Status } from "../api";

export default function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge ${status}`}>{status}</span>;
}
