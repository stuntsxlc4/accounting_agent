import { Group, Stack, Title } from '@mantine/core'
import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle?: ReactNode
  children?: ReactNode
}

export function PageHeader({ title, subtitle, children }: Props) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg" gap="md">
      <Stack gap={4} style={{ minWidth: 0, flex: '1 1 260px' }}>
        <Title order={2}>{title}</Title>
        {subtitle}
      </Stack>
      {children ? (
        <Group align="flex-end" gap="sm">
          {children}
        </Group>
      ) : null}
    </Group>
  )
}
