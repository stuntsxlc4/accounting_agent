import { Card, Skeleton, Stack } from '@mantine/core'

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Skeleton height={18} width="40%" />
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} height={34} />
        ))}
      </Stack>
    </Card>
  )
}

export function CardSkeleton() {
  return (
    <Card withBorder padding="lg">
      <Stack gap="sm">
        <Skeleton height={20} width="50%" />
        <Skeleton height={14} />
        <Skeleton height={14} width="80%" />
      </Stack>
    </Card>
  )
}
