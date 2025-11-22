// Mock data for development - will be replaced by events.json from Python scraper

export interface Movie {
  title: string;
  year?: number;
  time: string;
  duration?: string;
  language?: string;
  subtitles?: string;
  rating?: string;
  url?: string;
}

export interface MovieDay {
  day: string;
  date: string;
  movies: Movie[];
}

export interface Concert {
  title: string;
  date: string;
  day: string;
  time?: string;
  venue: string;
  url?: string;
}

export interface EventData {
  meta: {
    week: number;
    year: number;
    updatedAt: string;
  };
  movies: MovieDay[];
  concerts: Concert[];
}

// Mock data matching the planned UI
export const mockData: EventData = {
  meta: {
    week: 47,
    year: 2025,
    updatedAt: "Mon 18 Nov 09:00"
  },
  movies: [
    {
      day: "FRI",
      date: "21.11",
      movies: [
        {
          title: "Chainsaw Man: Reze Arc",
          year: 2025,
          time: "22:50",
          duration: "1h41m",
          language: "JP",
          subtitles: "DE",
          rating: "FSK16",
          url: "https://example.com/chainsaw-man"
        }
      ]
    },
    {
      day: "SAT",
      date: "22.11",
      movies: [
        {
          title: "Gladiator II",
          year: 2024,
          time: "19:30",
          duration: "2h28m",
          language: "EN",
          subtitles: "DE",
          rating: "FSK16",
          url: "https://example.com/gladiator"
        },
        {
          title: "Wicked",
          year: 2024,
          time: "20:00",
          duration: "2h40m",
          language: "EN",
          subtitles: "DE",
          rating: "FSK6",
          url: "https://example.com/wicked"
        },
        {
          title: "Conclave",
          year: 2024,
          time: "17:15",
          duration: "2h00m",
          language: "EN",
          subtitles: "DE",
          rating: "FSK12",
          url: "https://example.com/conclave"
        }
      ]
    },
    {
      day: "SUN",
      date: "23.11",
      movies: [
        {
          title: "The Substance",
          year: 2024,
          time: "20:30",
          duration: "2h20m",
          language: "EN",
          rating: "FSK18",
          url: "https://example.com/substance"
        }
      ]
    }
  ],
  concerts: [
    {
      title: "Luciano",
      date: "29 Nov",
      day: "Sa",
      time: "20:00",
      venue: "ZAG Arena",
      url: "https://example.com/luciano"
    },
    {
      title: "Simply Red",
      date: "05 Dec",
      day: "Fr",
      time: "20:00",
      venue: "Swiss Life Hall",
      url: "https://example.com/simply-red"
    },
    {
      title: "Mat Kearney",
      date: "12 Dec",
      day: "Fr",
      time: "19:30",
      venue: "MusikZentrum",
      url: "https://example.com/mat-kearney"
    },
    {
      title: "Scooter",
      date: "14 Dec",
      day: "Sa",
      time: "20:00",
      venue: "ZAG Arena",
      url: "https://example.com/scooter"
    },
    {
      title: "Deichkind",
      date: "21 Dec",
      day: "Sa",
      time: "19:30",
      venue: "ZAG Arena",
      url: "https://example.com/deichkind"
    },
    {
      title: "Helene Fischer",
      date: "28 Mar",
      day: "Fr",
      time: "20:00",
      venue: "ZAG Arena",
      url: "https://example.com/helene-fischer"
    }
  ]
};
