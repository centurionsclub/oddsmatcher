import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

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

  const allSelected = selected.length === options.length;

  const handleToggle = (value: string) => {
    const newSelected = selected.includes(value)
      ? selected.filter((item) => item !== value)
      : [...selected, value];
    onChange(newSelected);
  };

  const handleSelectAll = () => {
    if (allSelected) {
      onChange([]);
    } else {
      onChange(options.map(o => o.value));
    }
  };

  const displayText = selected.length === 0
    ? "Tutti i bookmakers"
    : allSelected
    ? "Tutti selezionati"
    : selected.length === 1
    ? options.find(opt => opt.value === selected[0])?.label || "1 selezionato"
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
        <div className="max-h-[400px] overflow-y-auto p-2">
          {/* Seleziona Tutti */}
          <div
            className={cn(
              "flex items-center px-3 py-1.5 cursor-pointer rounded text-sm font-medium mb-1",
              allSelected
                ? "bg-[#29B6F6] text-white"
                : "hover:bg-secondary/50"
            )}
            onClick={handleSelectAll}
          >
            Seleziona Tutti
          </div>

          <div className="my-1 h-px bg-border" />

          {options.map((option) => {
            const isSelected = selected.includes(option.value);
            return (
              <div
                key={option.value}
                className={cn(
                  "flex items-center px-3 py-1.5 cursor-pointer rounded text-sm",
                  isSelected
                    ? "bg-[#29B6F6] text-white"
                    : "hover:bg-secondary/50"
                )}
                onClick={() => handleToggle(option.value)}
              >
                {option.label}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
