import { Group, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg">
      <Stack gap={2}>
        <Title order={2}>{title}</Title>
        {subtitle ? <Text c="dimmed">{subtitle}</Text> : null}
      </Stack>
      {children ? <Group align="flex-end">{children}</Group> : null}
    </Group>
  )
}
