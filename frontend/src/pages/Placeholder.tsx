interface PlaceholderProps {
  title: string
}

export default function Placeholder({ title }: PlaceholderProps) {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold">{title}</h1>
      <p className="text-gray-500 mt-2">This portal will be built in a later step.</p>
    </div>
  )
}