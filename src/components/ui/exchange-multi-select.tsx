import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

interface ExchangeMultiSelectProps {
  selected: string[];
  onChange: (selected: string[]) => void;
  betfairCommission: string;
  betflagCommission: string;
  onBetfairChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onBetflagChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  className?: string;
}

const bookmakers = [
  { value: "888sport", label: "888sport" },
  { value: "admiral", label: "Admiral" },
  { value: "bet365", label: "Bet365" },
  { value: "betfair-book", label: "Betfair" },
  { value: "betflag-book", label: "Betflag" },
  { value: "betsson", label: "Betsson" },
  { value: "better", label: "Better" },
  { value: "betway", label: "Betway" },
  { value: "eurobet", label: "Eurobet" },
  { value: "goldbet", label: "Goldbet" },
  { value: "lottomatica", label: "Lottomatica" },
  { value: "netbet", label: "NetBet" },
  { value: "sisal", label: "Sisal" },
  { value: "snai", label: "Snai" },
  { value: "unibet", label: "Unibet" },
  { value: "williamhill", label: "William Hill" },
];

export function ExchangeMultiSelect({
  selected,
  onChange,
  betfairCommission,
  betflagCommission,
  onBetfairChange,
  onBetflagChange,
  className,
}: ExchangeMultiSelectProps) {
  const [open, setOpen] = React.useState(false);

  const handleToggle = (value: string) => {
    const newSelected = selected.includes(value)
      ? selected.filter((item) => item !== value)
      : [...selected, value];
    
    onChange(newSelected);
  };

  const displayText = selected.length === 0 
    ? "Tutti gli Exchange" 
    : selected.length === 1
    ? (selected[0] === "betfair" ? "Betfair Exchange" : 
       selected[0] === "betflag" ? "BetFlag Exchange" : 
       bookmakers.find(b => b.value === selected[0])?.label || "Selezionato")
    : `${selected.length} selezionati`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "justify-between bg-white border-gray-300 h-9",
            className
          )}
        >
          {displayText}
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent 
        className="w-[400px] p-0 bg-white z-50" 
        align="start"
        side="bottom"
      >
        <div className="max-h-[400px] overflow-y-auto">
          <div className="p-2">
            {/* Opzione "Tutti" */}
            <div
              className="flex items-center space-x-2 px-2 py-2 hover:bg-gray-100 cursor-pointer rounded"
              onClick={() => onChange([])}
            >
              <Checkbox
                checked={selected.length === 0}
                onCheckedChange={() => onChange([])}
              />
              <span className="text-sm font-medium">Tutti gli Exchange</span>
            </div>
            
            {/* Separatore */}
            <div className="my-1 h-px bg-gray-200" />
            
            {/* Betfair con commissione */}
            <div className="flex items-center justify-between px-2 py-2 hover:bg-gray-100 rounded">
              <div 
                className="flex items-center space-x-2 flex-1 cursor-pointer"
                onClick={() => handleToggle("betfair")}
              >
                <Checkbox
                  checked={selected.includes("betfair")}
                  onCheckedChange={() => handleToggle("betfair")}
                />
                <span className="text-sm">Betfair Exchange</span>
              </div>
              <Input 
                type="text" 
                value={betfairCommission}
                onChange={onBetfairChange}
                className="h-7 w-20 text-xs ml-2"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
            
            {/* Betflag con commissione */}
            <div className="flex items-center justify-between px-2 py-2 hover:bg-gray-100 rounded">
              <div 
                className="flex items-center space-x-2 flex-1 cursor-pointer"
                onClick={() => handleToggle("betflag")}
              >
                <Checkbox
                  checked={selected.includes("betflag")}
                  onCheckedChange={() => handleToggle("betflag")}
                />
                <span className="text-sm">BetFlag Exchange</span>
              </div>
              <Input 
                type="text" 
                value={betflagCommission}
                onChange={onBetflagChange}
                className="h-7 w-20 text-xs ml-2"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
            
            {/* Separatore Bookmakers */}
            <div className="px-2 py-2 text-sm font-semibold text-gray-700 bg-gray-100 border-t border-b border-gray-200 mt-1 mb-1">
              Bookmakers
            </div>
            
            {/* Bookmakers */}
            {bookmakers.map((bookmaker) => (
              <div
                key={bookmaker.value}
                className="flex items-center space-x-2 px-2 py-2 hover:bg-gray-100 cursor-pointer rounded"
                onClick={() => handleToggle(bookmaker.value)}
              >
                <Checkbox
                  checked={selected.includes(bookmaker.value)}
                  onCheckedChange={() => handleToggle(bookmaker.value)}
                />
                <span className="text-sm">{bookmaker.label}</span>
              </div>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
