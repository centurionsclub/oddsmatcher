export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "13.0.5"
  }
  public: {
    Tables: {
      aggregated_odds: {
        Row: {
          best_back_bookmaker: string | null
          best_back_odds: number | null
          best_lay_bookmaker: string | null
          best_lay_odds: number | null
          event_id: string | null
          id: string
          market: string
          outcome: string
          updated_at: string | null
        }
        Insert: {
          best_back_bookmaker?: string | null
          best_back_odds?: number | null
          best_lay_bookmaker?: string | null
          best_lay_odds?: number | null
          event_id?: string | null
          id?: string
          market: string
          outcome: string
          updated_at?: string | null
        }
        Update: {
          best_back_bookmaker?: string | null
          best_back_odds?: number | null
          best_lay_bookmaker?: string | null
          best_lay_odds?: number | null
          event_id?: string | null
          id?: string
          market?: string
          outcome?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "aggregated_odds_event_id_fkey"
            columns: ["event_id"]
            isOneToOne: false
            referencedRelation: "events_master"
            referencedColumns: ["id"]
          },
        ]
      }
      events_master: {
        Row: {
          created_at: string
          event_name: string
          event_time: string
          id: string
          league: string
          normalized_name: string
          sport: string
        }
        Insert: {
          created_at?: string
          event_name: string
          event_time: string
          id?: string
          league: string
          normalized_name: string
          sport: string
        }
        Update: {
          created_at?: string
          event_name?: string
          event_time?: string
          id?: string
          league?: string
          normalized_name?: string
          sport?: string
        }
        Relationships: []
      }
      matched_bets: {
        Row: {
          back_bookmaker: string
          back_odds: number
          back_stake: number
          commission_rate: number | null
          created_at: string | null
          event_id: string | null
          expires_at: string | null
          id: string
          lay_bookmaker: string
          lay_odds: number
          lay_stake: number
          market: string
          outcome: string
          profit: number
          rating: number
        }
        Insert: {
          back_bookmaker: string
          back_odds: number
          back_stake: number
          commission_rate?: number | null
          created_at?: string | null
          event_id?: string | null
          expires_at?: string | null
          id?: string
          lay_bookmaker?: string
          lay_odds: number
          lay_stake: number
          market: string
          outcome: string
          profit: number
          rating: number
        }
        Update: {
          back_bookmaker?: string
          back_odds?: number
          back_stake?: number
          commission_rate?: number | null
          created_at?: string | null
          event_id?: string | null
          expires_at?: string | null
          id?: string
          lay_bookmaker?: string
          lay_odds?: number
          lay_stake?: number
          market?: string
          outcome?: string
          profit?: number
          rating?: number
        }
        Relationships: [
          {
            foreignKeyName: "matched_bets_event_id_fkey"
            columns: ["event_id"]
            isOneToOne: false
            referencedRelation: "events_master"
            referencedColumns: ["id"]
          },
        ]
      }
      odds_cache: {
        Row: {
          bookmaker: string
          event_name: string
          event_time: string | null
          expires_at: string
          id: string
          league: string | null
          market: string
          odds: Json
          scraped_at: string
          sport: string
        }
        Insert: {
          bookmaker: string
          event_name: string
          event_time?: string | null
          expires_at?: string
          id?: string
          league?: string | null
          market: string
          odds: Json
          scraped_at?: string
          sport: string
        }
        Update: {
          bookmaker?: string
          event_name?: string
          event_time?: string | null
          expires_at?: string
          id?: string
          league?: string | null
          market?: string
          odds?: Json
          scraped_at?: string
          sport?: string
        }
        Relationships: []
      }
      saved_filters: {
        Row: {
          created_at: string
          filter_data: Json
          id: string
          name: string
          tab_type: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          filter_data: Json
          id?: string
          name: string
          tab_type: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          filter_data?: Json
          id?: string
          name?: string
          tab_type?: string
          updated_at?: string
        }
        Relationships: []
      }
      scraping_logs: {
        Row: {
          bookmaker: string
          created_at: string
          duration_ms: number | null
          error_message: string | null
          id: string
          status: string
        }
        Insert: {
          bookmaker: string
          created_at?: string
          duration_ms?: number | null
          error_message?: string | null
          id?: string
          status: string
        }
        Update: {
          bookmaker?: string
          created_at?: string
          duration_ms?: number | null
          error_message?: string | null
          id?: string
          status?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      clean_expired_matched_bets: { Args: never; Returns: undefined }
      clean_expired_odds_cache: { Args: never; Returns: undefined }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
