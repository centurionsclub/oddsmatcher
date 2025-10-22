import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CalendarIcon, Filter, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { format } from "date-fns";
import { it } from "date-fns/locale";

export const FilterSidebar = () => {
  const [dateFrom, setDateFrom] = useState<Date>();
  const [dateTo, setDateTo] = useState<Date>();

  return (
    <Card className="p-6 space-y-6 sticky top-24">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Filter className="h-5 w-5 text-primary" />
          Filtri
        </h2>
        <Button variant="ghost" size="sm">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Sport */}
      <div className="space-y-2">
        <Label htmlFor="sport">Sport</Label>
        <Select defaultValue="tutti">
          <SelectTrigger id="sport">
            <SelectValue placeholder="Seleziona sport" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti gli sport</SelectItem>
            <SelectItem value="calcio">⚽ Calcio</SelectItem>
            <SelectItem value="tennis">🎾 Tennis</SelectItem>
            <SelectItem value="basket">🏀 Basket</SelectItem>
            <SelectItem value="volley">🏐 Volley</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Mercato */}
      <div className="space-y-2">
        <Label htmlFor="mercato">Mercato</Label>
        <Select defaultValue="tutti">
          <SelectTrigger id="mercato">
            <SelectValue placeholder="Seleziona mercato" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti i mercati</SelectItem>
            <SelectItem value="1x2">1X2</SelectItem>
            <SelectItem value="over-under">Over/Under</SelectItem>
            <SelectItem value="gol">Gol No Gol</SelectItem>
            <SelectItem value="handicap">Handicap</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Bookmaker */}
      <div className="space-y-2">
        <Label htmlFor="bookmaker">Bookmaker</Label>
        <Select defaultValue="tutti">
          <SelectTrigger id="bookmaker">
            <SelectValue placeholder="Seleziona bookmaker" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti i bookmaker</SelectItem>
            <SelectItem value="bet365">Bet365</SelectItem>
            <SelectItem value="sisal">Sisal</SelectItem>
            <SelectItem value="snai">Snai</SelectItem>
            <SelectItem value="eurobet">Eurobet</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Exchange */}
      <div className="space-y-2">
        <Label htmlFor="exchange">Exchange</Label>
        <Select defaultValue="tutti">
          <SelectTrigger id="exchange">
            <SelectValue placeholder="Seleziona exchange" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti gli exchange</SelectItem>
            <SelectItem value="betfair">Betfair</SelectItem>
            <SelectItem value="betflag">Betflag Exchange</SelectItem>
            <SelectItem value="matchbook">Matchbook</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Stake */}
      <div className="space-y-2">
        <Label htmlFor="stake">Stake Puntata (€)</Label>
        <Input id="stake" type="number" placeholder="50" defaultValue="50" />
      </div>

      {/* Tipo Bonus */}
      <div className="space-y-3">
        <Label>Tipo Bonus</Label>
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <Checkbox id="standard" defaultChecked />
            <label htmlFor="standard" className="text-sm cursor-pointer">Standard</label>
          </div>
          <div className="flex items-center space-x-2">
            <Checkbox id="rimborso" />
            <label htmlFor="rimborso" className="text-sm cursor-pointer">Rimborso</label>
          </div>
          <div className="flex items-center space-x-2">
            <Checkbox id="freebet" />
            <label htmlFor="freebet" className="text-sm cursor-pointer">Free Bet</label>
          </div>
        </div>
      </div>

      {/* Quote Min/Max */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="quotamin">Quota Min</Label>
          <Input id="quotamin" type="number" step="0.1" placeholder="1.5" defaultValue="1.5" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="quotamax">Quota Max</Label>
          <Input id="quotamax" type="number" step="0.1" placeholder="10" defaultValue="10" />
        </div>
      </div>

      {/* Date Range */}
      <div className="space-y-2">
        <Label>Periodo Evento</Label>
        <div className="grid gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="justify-start text-left font-normal">
                <CalendarIcon className="mr-2 h-4 w-4" />
                {dateFrom ? format(dateFrom, "PPP", { locale: it }) : "Data inizio"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar mode="single" selected={dateFrom} onSelect={setDateFrom} initialFocus />
            </PopoverContent>
          </Popover>

          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="justify-start text-left font-normal">
                <CalendarIcon className="mr-2 h-4 w-4" />
                {dateTo ? format(dateTo, "PPP", { locale: it }) : "Data fine"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar mode="single" selected={dateTo} onSelect={setDateTo} initialFocus />
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="space-y-2 pt-4 border-t">
        <Button className="w-full" size="lg">
          <Filter className="mr-2 h-4 w-4" />
          Applica Filtri
        </Button>
        <Button variant="outline" className="w-full">
          <RefreshCw className="mr-2 h-4 w-4" />
          Aggiorna Quote
        </Button>
      </div>
    </Card>
  );
};
