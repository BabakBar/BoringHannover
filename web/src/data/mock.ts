// Mock data for development - will be replaced by web_events.json from Python scraper
import type { EventData } from './types';

// Re-export types for convenience
export type { EventData, Movie, MovieDay, Concert, EventMeta } from './types';

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
          genre: "Animation",
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
          genre: "Action",
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
          genre: "Musical",
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
          genre: "Drama",
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
          genre: "Horror",
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
      url: "https://example.com/luciano",
      eventType: "concert",
      genre: "Electronic",
      description: "The Swiss-Chilean DJ brings his iconic sound to Hannover"
    },
    {
      title: "Simply Red",
      date: "05 Dec",
      day: "Fr",
      time: "20:00",
      venue: "Swiss Life Hall",
      url: "https://example.com/simply-red",
      eventType: "concert",
      genre: "Pop",
      status: "sold_out"
    },
    {
      title: "Mat Kearney",
      date: "12 Dec",
      day: "Fr",
      time: "19:30",
      venue: "MusikZentrum",
      url: "https://example.com/mat-kearney",
      eventType: "concert",
      genre: "Indie"
    },
    {
      title: "Scooter",
      date: "14 Dec",
      day: "Sa",
      time: "20:00",
      venue: "ZAG Arena",
      url: "https://example.com/scooter",
      eventType: "concert",
      genre: "Techno",
      description: "Hyper Hyper Tour 2025"
    },
    {
      title: "Comedy Night",
      date: "21 Dec",
      day: "Sa",
      time: "19:30",
      venue: "Capitol Hannover",
      url: "https://example.com/comedy",
      eventType: "show",
      description: "Stand-up comedy featuring local and international acts"
    },
    {
      title: "Helene Fischer",
      date: "28 Mar",
      day: "Fr",
      time: "20:00",
      venue: "ZAG Arena",
      url: "https://example.com/helene-fischer",
      eventType: "concert",
      genre: "Schlager"
    }
  ]
};
