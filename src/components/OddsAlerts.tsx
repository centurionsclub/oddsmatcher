import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bell, X } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useToast } from "@/hooks/use-toast";
import { format } from "date-fns";

interface Alert {
  id: string;
  event_name: string;
  outcome: string;
  bookmaker: string;
  odds: number;
  average_odds: number;
  difference_percentage: number;
  event_time: string;
  created_at: string;
  is_read: boolean;
}

export function OddsAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const { toast } = useToast();

  useEffect(() => {
    const loadAlerts = async () => {
      const { data, error } = await supabase
        .from('odds_alerts')
        .select('*')
        .eq('is_read', false)
        .gt('expires_at', new Date().toISOString())
        .order('created_at', { ascending: false })
        .limit(10);
      
      if (!error && data) {
        setAlerts(data);
      }
    };
    
    loadAlerts();
    
    // Realtime subscription for new alerts
    const channel = supabase
      .channel('odds_alerts_channel')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'odds_alerts'
        },
        (payload) => {
          const newAlert = payload.new as Alert;
          setAlerts(prev => [newAlert, ...prev].slice(0, 10));
          
          // Show toast notification
          toast({
            title: "🔔 Quota Anomala Rilevata!",
            description: `${newAlert.bookmaker} ha ${newAlert.odds} per ${newAlert.event_name} (${newAlert.outcome}) - ${newAlert.difference_percentage}% sopra la media!`,
            duration: 10000,
          });
        }
      )
      .subscribe();
    
    return () => {
      supabase.removeChannel(channel);
    };
  }, [toast]);

  const markAsRead = async (id: string) => {
    const { error } = await supabase
      .from('odds_alerts')
      .update({ is_read: true })
      .eq('id', id);
    
    if (!error) {
      setAlerts(prev => prev.filter(alert => alert.id !== id));
    }
  };

  const dismissAll = async () => {
    const ids = alerts.map(a => a.id);
    await supabase
      .from('odds_alerts')
      .update({ is_read: true })
      .in('id', ids);
    
    setAlerts([]);
  };

  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 w-96 max-h-[500px] overflow-y-auto space-y-2 z-50">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Bell className="h-4 w-4" />
          Alert Quote ({alerts.length})
        </h3>
        <Button 
          size="sm" 
          variant="ghost" 
          onClick={dismissAll}
          className="h-6 text-xs"
        >
          Chiudi tutto
        </Button>
      </div>
      
      {alerts.map(alert => (
        <Card 
          key={alert.id} 
          className="bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800 shadow-lg"
        >
          <CardHeader className="pb-2 pt-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 flex-1">
                <Bell className="h-4 w-4 text-orange-600 dark:text-orange-400 flex-shrink-0" />
                <p className="text-sm font-semibold leading-tight">{alert.event_name}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => markAsRead(alert.id)}
                className="h-6 w-6 p-0"
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pb-3">
            <div className="space-y-1">
              <p className="text-xs">
                <span className="font-bold capitalize">{alert.bookmaker}</span> ha{' '}
                <span className="text-green-600 dark:text-green-400 font-bold text-sm">
                  {alert.odds}
                </span>{' '}
                per{' '}
                <span className="font-medium">{alert.outcome}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                Media: {alert.average_odds} • Differenza: <span className="font-bold text-orange-600 dark:text-orange-400">+{alert.difference_percentage}%</span>
              </p>
              <p className="text-xs text-muted-foreground">
                {format(new Date(alert.created_at), "HH:mm:ss")}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
