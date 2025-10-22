import * as React from "react";
import { cn } from "@/lib/utils";

interface DecimalInputProps extends Omit<React.ComponentProps<"input">, "onChange" | "value"> {
  value: string;
  onChange: (value: string) => void;
}

const DecimalInput = React.forwardRef<HTMLInputElement, DecimalInputProps>(
  ({ className, value, onChange, ...props }, ref) => {
    const [displayValue, setDisplayValue] = React.useState(value);

    React.useEffect(() => {
      setDisplayValue(value);
    }, [value]);

    const formatDecimal = (input: string) => {
      // Rimuovi tutto tranne i numeri
      const numbers = input.replace(/[^\d]/g, '');
      
      if (numbers === '' || numbers === '0') {
        return '0,00';
      }

      // Converti a numero e formatta con la virgola
      const num = parseInt(numbers, 10);
      const formatted = (num / 100).toFixed(2).replace('.', ',');
      
      return formatted;
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const input = e.target.value;
      
      // Se l'utente cancella tutto
      if (input === '') {
        setDisplayValue('0,00');
        onChange('0,00');
        return;
      }

      // Formatta il valore
      const formatted = formatDecimal(input);
      setDisplayValue(formatted);
      onChange(formatted);
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
      // Quando l'utente fa focus, seleziona tutto il testo per facilitare la digitazione
      e.target.select();
    };

    return (
      <input
        type="text"
        inputMode="decimal"
        className={cn(
          "flex h-10 w-full rounded-md border border-border bg-[#66BB6A] px-3 py-2 text-base text-white ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-white placeholder:text-white/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        value={displayValue}
        onChange={handleChange}
        onFocus={handleFocus}
        {...props}
      />
    );
  },
);
DecimalInput.displayName = "DecimalInput";

export { DecimalInput };
