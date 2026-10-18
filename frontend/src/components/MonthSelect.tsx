import { MonthPickerInput } from '@mantine/dates'
import { IconCalendarMonth } from '@tabler/icons-react'
import { useState } from 'react'
import { dateToMonth, monthToDate } from '../format'

interface Props {
  month: string
  onChange: (month: string) => void
  disabled?: boolean
}

export function MonthSelect({ month, onChange, disabled }: Props) {
  const [today] = useState(() => new Date())
  return (
    <MonthPickerInput
      label="Miesiąc"
      value={monthToDate(month)}
      onChange={(value) => value && onChange(dateToMonth(value))}
      valueFormat="MMMM YYYY"
      leftSection={<IconCalendarMonth size={18} stroke={1.6} />}
      maxDate={today}
      disabled={disabled}
      w={220}
      styles={{ input: { textTransform: 'capitalize' } }}
    />
  )
}
