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
    },
    // Additional events for pagination testing
    { title: "Ed Sheeran", date: "02 Apr", day: "Mi", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Pop" },
    { title: "Rammstein", date: "05 Apr", day: "Sa", time: "19:30", venue: "ZAG Arena", eventType: "concert", genre: "Metal" },
    { title: "Coldplay", date: "10 Apr", day: "Do", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Rock" },
    { title: "The Weeknd", date: "15 Apr", day: "Di", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "R&B" },
    { title: "Taylor Swift", date: "20 Apr", day: "So", time: "19:00", venue: "ZAG Arena", eventType: "concert", genre: "Pop", status: "sold_out" },
    { title: "Depeche Mode", date: "25 Apr", day: "Fr", time: "20:00", venue: "Swiss Life Hall", eventType: "concert", genre: "Electronic" },
    { title: "Kraftwerk", date: "28 Apr", day: "Mo", time: "20:00", venue: "Capitol Hannover", eventType: "concert", genre: "Electronic" },
    { title: "Metallica", date: "02 May", day: "Fr", time: "19:30", venue: "ZAG Arena", eventType: "concert", genre: "Metal" },
    { title: "Adele", date: "08 May", day: "Do", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Pop", status: "sold_out" },
    { title: "Die Ärzte", date: "12 May", day: "Mo", time: "19:30", venue: "Swiss Life Hall", eventType: "concert", genre: "Punk Rock" },
    { title: "Hans Zimmer Live", date: "18 May", day: "So", time: "19:00", venue: "ZAG Arena", eventType: "concert", genre: "Orchestra" },
    { title: "Iron Maiden", date: "22 May", day: "Do", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Metal" },
    { title: "Billie Eilish", date: "28 May", day: "Mi", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Pop" },
    { title: "Green Day", date: "01 Jun", day: "So", time: "19:30", venue: "Swiss Life Hall", eventType: "concert", genre: "Punk Rock" },
    { title: "Linkin Park", date: "05 Jun", day: "Do", time: "20:00", venue: "ZAG Arena", eventType: "concert", genre: "Rock" }
  ]
};
