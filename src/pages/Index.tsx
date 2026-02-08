import Navbar from "@/components/Navbar";
import AnnouncementBanner from "@/components/AnnouncementBanner";
import HeroSection from "@/components/HeroSection";
import Footer from "@/components/Footer";

const Index = () => {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <div className="pt-14">
        <AnnouncementBanner />
      </div>
      <HeroSection />
      <Footer />
    </div>
  );
};

export default Index;
