import * as React from "react";
import { cn } from "@/lib/utils";

interface CurrencyInputProps extends Omit<React.ComponentProps<"input">, "onChange" | "value"> {
  value: string;
  onChange: (value: string) => void;
}

const CurrencyInput = React.forwardRef<HTMLInputElement, CurrencyInputProps>(
  ({ className, value, onChange, ...props }, ref) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      let input = e.target.value;
      
      // Rimuovi il simbolo € se presente
      input = input.replace(/€/g, '').trim();
      
      // Permetti solo numeri, virgola e punto
      input = input.replace(/[^\d,\.]/g, '');
      
      // Sostituisci il punto con la virgola
      input = input.replace(/\./g, ',');
      
      // Permetti solo una virgola
      const parts = input.split(',');
      if (parts.length > 2) {
        input = parts[0] + ',' + parts.slice(1).join('');
      }
      
      // Limita a 2 decimali dopo la virgola
      if (parts.length === 2 && parts[1].length > 2) {
        input = parts[0] + ',' + parts[1].substring(0, 2);
      }
      
      onChange(input);
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
      // Quando l'utente fa focus, seleziona tutto il testo
      e.target.select();
    };

    // Mostra il valore con € davanti
    const displayValue = value ? `€ ${value}` : '€ 0';

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
CurrencyInput.displayName = "CurrencyInput";

export { CurrencyInput };
