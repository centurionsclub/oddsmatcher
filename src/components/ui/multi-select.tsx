import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";

interface MultiSelectProps {
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
  className?: string;
}

export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = "Seleziona...",
  className,
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false);

  const handleToggle = (value: string) => {
    if (value === "tutti") {
      // Se seleziona "tutti", deseleziona tutto
      onChange([]);
      return;
    }

    const newSelected = selected.includes(value)
      ? selected.filter((item) => item !== value)
      : [...selected, value];
    
    onChange(newSelected);
  };

  const displayText = selected.length === 0 
    ? "Tutti i bookmakers" 
    : selected.length === 1
    ? options.find(opt => opt.value === selected[0])?.label || "Selezionati"
    : `${selected.length} selezionati`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
            className={cn(
              "justify-between h-9 bg-background border border-border text-foreground hover:bg-background/90",
              className
            )}
        >
          {displayText}
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent 
        className="w-[300px] p-0 z-50" 
        align="start"
        side="bottom"
        sideOffset={4}
        avoidCollisions={false}
      >
        <div className="max-h-[400px] overflow-y-auto">
          <div className="p-2">
            {/* Opzione "Tutti" */}
            <div
              className="flex items-center space-x-2 px-2 py-2 hover:bg-secondary/50 cursor-pointer rounded"
              onClick={() => onChange([])}
            >
              <Checkbox
                checked={selected.length === 0}
                onCheckedChange={() => onChange([])}
              />
              <span className="text-sm font-medium">Tutti i bookmakers</span>
            </div>
            
            {/* Separatore */}
            <div className="my-1 h-px bg-border" />
            
            {/* Opzioni multiple */}
            {options.map((option) => (
              <div
                key={option.value}
                className="flex items-center space-x-2 px-2 py-2 hover:bg-secondary/50 cursor-pointer rounded"
                onClick={() => handleToggle(option.value)}
              >
                <Checkbox
                  checked={selected.includes(option.value)}
                  onCheckedChange={() => handleToggle(option.value)}
                />
                <span className="text-sm">{option.label}</span>
              </div>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
