import { Anchor, Group, Text, Tooltip } from '@mantine/core'
import { IconFolder } from '@tabler/icons-react'
import { shortPath } from '../format'

interface Props {
  path: string
  onOpen?: () => void
  parts?: number
}

/** Krótka ścieżka folderu z pełną w podpowiedzi; kliknięcie otwiera folder. */
export function PathLabel({ path, onOpen, parts = 2 }: Props) {
  const label = (
    <Group gap={6} wrap="nowrap">
      <IconFolder size={15} stroke={1.6} style={{ flexShrink: 0 }} />
      <Text size="sm" c="dimmed" truncate>
        {shortPath(path, parts)}
      </Text>
    </Group>
  )
  return (
    <Tooltip label={path} multiline maw={520} openDelay={300} withArrow>
      {onOpen ? (
        <Anchor component="button" type="button" onClick={onOpen} underline="hover" c="dimmed">
          {label}
        </Anchor>
      ) : (
        label
      )}
    </Tooltip>
  )
}
