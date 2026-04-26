export default function Empty({ message }: { message: string }) {
  return (
    <div className="panel text-center text-sm text-muted">
      {message}
    </div>
  );
}
